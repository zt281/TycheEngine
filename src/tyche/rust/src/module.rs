//! TycheModuleBase - Reusable ZeroMQ module foundation.
//!
//! Handles registration, socket lifecycle, heartbeat, and event dispatch.
//! Concrete modules provide a dispatcher closure to handle incoming events.

use crate::message::{deserialize_message, serialize_message};
use crate::types::{Interface, Message, Payload};
use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Arc, Condvar, Mutex};
use std::thread;
use std::time::Duration;

const HEARTBEAT_INTERVAL: f64 = 1.0;

/// Pending job request state.
struct PendingRequest {
    result: Mutex<Option<Payload>>,
    ready: Condvar,
}

/// Base module providing core ZMQ connectivity and lifecycle.
///
/// Use `start_with_dispatcher` to connect to TycheEngine and begin
/// receiving events. The dispatcher closure is called on the event
/// receiver thread for each incoming message.
pub struct TycheModuleBase {
    pub family_name: String,
    pub module_id: Mutex<String>,
    pub engine_endpoint: String,
    pub heartbeat_receive_endpoint: Option<String>,
    pub interfaces: Vec<Interface>,

    running: AtomicBool,
    registered: AtomicBool,
    pub_socket: Mutex<Option<Arc<Mutex<zmq::Socket>>>>,
    sub_socket: Mutex<Option<Arc<Mutex<zmq::Socket>>>>,
    heartbeat_socket: Mutex<Option<Arc<Mutex<zmq::Socket>>>>,
    job_socket: Mutex<Option<Arc<Mutex<zmq::Socket>>>>,
    engine_pub_port: Mutex<Option<u16>>,
    engine_sub_port: Mutex<Option<u16>>,
    engine_job_port: Mutex<Option<u16>>,
    context: Mutex<Option<zmq::Context>>,
    threads: Mutex<Vec<thread::JoinHandle<()>>>,
    stop_senders: Mutex<Vec<mpsc::Sender<()>>>,

    /// Job handler registry: event_name -> handler function.
    job_handlers: Mutex<HashMap<String, Arc<dyn Fn(&Payload) -> Payload + Send + Sync>>>,

    /// Pending job requests: correlation_id -> pending state.
    pending_requests: Arc<Mutex<HashMap<String, Arc<PendingRequest>>>>,
}

impl TycheModuleBase {
    /// Create a new module base.
    ///
    /// `family_name` identifies the module type (e.g. "greeks_engine").
    /// The actual `module_id` is assigned by the Engine during registration.
    pub fn new(
        family_name: String,
        engine_endpoint: String,
        heartbeat_receive_endpoint: Option<String>,
        interfaces: Vec<Interface>,
    ) -> Self {
        Self {
            family_name: family_name.clone(),
            module_id: Mutex::new(family_name),
            engine_endpoint,
            heartbeat_receive_endpoint,
            interfaces,
            running: AtomicBool::new(false),
            registered: AtomicBool::new(false),
            pub_socket: Mutex::new(None),
            sub_socket: Mutex::new(None),
            heartbeat_socket: Mutex::new(None),
            job_socket: Mutex::new(None),
            engine_pub_port: Mutex::new(None),
            engine_sub_port: Mutex::new(None),
            engine_job_port: Mutex::new(None),
            context: Mutex::new(None),
            threads: Mutex::new(Vec::new()),
            stop_senders: Mutex::new(Vec::new()),
            job_handlers: Mutex::new(HashMap::new()),
            pending_requests: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    /// Return the engine-assigned module_id (or family_name before registration).
    pub fn get_module_id(&self) -> String {
        self.module_id.lock().unwrap().clone()
    }

    /// Check if the module is currently running.
    pub fn is_running(&self) -> bool {
        self.running.load(Ordering::Relaxed)
    }

    /// Check if the module is registered with the engine.
    pub fn is_registered(&self) -> bool {
        self.registered.load(Ordering::Relaxed)
    }

    /// Register a job handler (handle_* pattern).
    ///
    /// Job handlers receive a request payload and return a response payload.
    pub fn register_job_handler<F>(&self, name: &str, handler: F)
    where
        F: Fn(&Payload) -> Payload + Send + Sync + 'static,
    {
        let bare = if let Some(stripped) = name.strip_prefix("handle_") {
            stripped.to_string()
        } else {
            name.to_string()
        };
        self.job_handlers
            .lock()
            .unwrap()
            .insert(bare, Arc::new(handler));
    }

    /// Start the module: register with engine, create sockets, spawn worker threads.
    ///
    /// `dispatcher` is called on the event receiver thread for each message.
    pub fn start_with_dispatcher<F>(&self, dispatcher: F) -> Result<(), String>
    where
        F: Fn(&str, &Message) + Send + Sync + 'static,
    {
        if self.running.load(Ordering::Relaxed) {
            return Ok(());
        }

        let context = zmq::Context::new();
        *self.context.lock().unwrap() = Some(context);

        if !self.register()? {
            return Err("Failed to register with engine".to_string());
        }

        // Create sockets
        {
            let ctx = self.context.lock().unwrap().as_ref().unwrap().clone();
            let host = extract_host(&self.engine_endpoint);
            let module_id = self.get_module_id();

            // PUB socket (module -> engine XSUB)
            if let Some(sub_port) = *self.engine_sub_port.lock().unwrap() {
                let sock = ctx.socket(zmq::PUB).map_err(|e| e.to_string())?;
                sock.set_linger(0).map_err(|e| e.to_string())?;
                sock.set_sndhwm(10000).map_err(|e| e.to_string())?;
                sock
                    .connect(&format!("tcp://{}:{}", host, sub_port))
                    .map_err(|e| e.to_string())?;
                *self.pub_socket.lock().unwrap() = Some(Arc::new(Mutex::new(sock)));
            }

            // SUB socket (engine XPUB -> module)
            if let Some(pub_port) = *self.engine_pub_port.lock().unwrap() {
                let sock = ctx.socket(zmq::SUB).map_err(|e| e.to_string())?;
                sock.set_linger(0).map_err(|e| e.to_string())?;
                sock.set_rcvhwm(10000).map_err(|e| e.to_string())?;
                sock
                    .set_rcvtimeo(100)
                    .map_err(|e| e.to_string())?;
                sock
                    .connect(&format!("tcp://{}:{}", host, pub_port))
                    .map_err(|e| e.to_string())?;

                // Subscribe to handler topics
                for iface in &self.interfaces {
                    if iface.pattern == "on" {
                        sock.set_subscribe(iface.event_type.as_bytes())
                            .map_err(|e| e.to_string())?;
                    }
                }

                *self.sub_socket.lock().unwrap() = Some(Arc::new(Mutex::new(sock)));
            }

            // HEARTBEAT socket
            if let Some(ref hb_endpoint) = self.heartbeat_receive_endpoint {
                let sock = ctx.socket(zmq::DEALER).map_err(|e| e.to_string())?;
                sock.set_linger(0).map_err(|e| e.to_string())?;
                sock.connect(hb_endpoint).map_err(|e| e.to_string())?;
                *self.heartbeat_socket.lock().unwrap() = Some(Arc::new(Mutex::new(sock)));
            }

            // JOB DEALER socket (for request/response communication)
            if let Some(job_port) = *self.engine_job_port.lock().unwrap() {
                let sock = ctx.socket(zmq::DEALER).map_err(|e| e.to_string())?;
                sock.set_linger(0).map_err(|e| e.to_string())?;
                sock.set_identity(module_id.as_bytes())
                    .map_err(|e| e.to_string())?;
                sock.set_rcvtimeo(100).map_err(|e| e.to_string())?;
                sock.connect(&format!("tcp://{}:{}", host, job_port))
                    .map_err(|e| e.to_string())?;
                *self.job_socket.lock().unwrap() = Some(Arc::new(Mutex::new(sock)));
            }
        }

        self.running.store(true, Ordering::Relaxed);

        // Start worker threads
        let (stop_tx1, stop_rx1) = mpsc::channel();
        let (stop_tx2, stop_rx2) = mpsc::channel();
        let (stop_tx3, stop_rx3) = mpsc::channel();

        let mut threads = vec![];

        // Event receiver thread
        if let Some(sub_socket) = self.sub_socket.lock().unwrap().as_ref() {
            let socket = Arc::clone(sub_socket);
            let module_id = self.get_module_id();
            let dispatcher = Arc::new(dispatcher);
            threads.push(thread::spawn(move || {
                event_receiver_loop(socket, module_id, stop_rx1, dispatcher);
            }));
        }

        // Heartbeat thread
        if let Some(hb_socket) = self.heartbeat_socket.lock().unwrap().as_ref() {
            let socket = Arc::clone(hb_socket);
            let module_id = self.get_module_id();
            threads.push(thread::spawn(move || {
                heartbeat_loop(socket, module_id, stop_rx2);
            }));
        }

        // Job receiver thread
        if let Some(job_socket) = self.job_socket.lock().unwrap().as_ref() {
            let socket = Arc::clone(job_socket);
            let module_id = self.get_module_id();
            let job_handlers = self.job_handlers.lock().unwrap().clone();
            let pending = Arc::clone(&self.pending_requests);
            threads.push(thread::spawn(move || {
                job_receiver_loop(socket, module_id, stop_rx3, job_handlers, pending);
            }));
        }

        *self.threads.lock().unwrap() = threads;
        *self.stop_senders.lock().unwrap() = vec![stop_tx1, stop_tx2, stop_tx3];

        Ok(())
    }

    /// Stop the module gracefully.
    pub fn stop(&self) {
        if !self.running.load(Ordering::Relaxed) {
            return;
        }

        self.running.store(false, Ordering::Relaxed);

        // Signal threads to stop
        {
            let senders = self.stop_senders.lock().unwrap();
            for sender in senders.iter() {
                let _ = sender.send(());
            }
        }

        // Wait for threads
        {
            let mut threads = self.threads.lock().unwrap();
            for t in threads.drain(..) {
                let _ = t.join();
            }
        }

        // Clean up sockets
        *self.pub_socket.lock().unwrap() = None;
        *self.sub_socket.lock().unwrap() = None;
        *self.heartbeat_socket.lock().unwrap() = None;
        *self.job_socket.lock().unwrap() = None;

        // Wake up pending request waiters
        {
            let pending = self.pending_requests.lock().unwrap();
            for (_, req) in pending.iter() {
                // Set result to Null so waiters unblock
                *req.result.lock().unwrap() = Some(serde_json::Value::Null);
                req.ready.notify_all();
            }
        }
        self.pending_requests.lock().unwrap().clear();

        // Clean up context
        *self.context.lock().unwrap() = None;

        self.registered.store(false, Ordering::Relaxed);
    }

    /// Publish an event through the engine's event proxy.
    pub fn send_event(&self, event: &str, payload: Payload, recipient: Option<String>) {
        let module_id = self.get_module_id();
        let msg = Message {
            msg_type: "evt".to_string(),
            sender: module_id.clone(),
            event: event.to_string(),
            payload,
            recipient,
            durability: 1,
            timestamp: None,
            correlation_id: None,
        };

        if let Some(pub_socket) = self.pub_socket.lock().unwrap().as_ref() {
            if let Ok(socket) = pub_socket.lock() {
                let data = serialize_message(&msg);
                let _ = socket.send_multipart([event.as_bytes(), &data], 0);
            }
        } else {
            eprintln!(
                "[{}] Cannot send event: not connected to event proxy",
                module_id
            );
        }
    }

    // -----------------------------------------------------------------------
    // Job Request/Response
    // -----------------------------------------------------------------------

    /// Send a job request and block until a response is received.
    ///
    /// Returns the response payload. Returns an error on timeout
    /// or if the job socket is not connected.
    pub fn request_event(
        &self,
        event: &str,
        payload: Payload,
        timeout: Duration,
    ) -> Result<Payload, String> {
        let module_id = self.get_module_id();
        let job_socket = self
            .job_socket
            .lock()
            .unwrap();
        let job_socket = job_socket
            .as_ref()
            .ok_or_else(|| {
                format!("[{}] Cannot request: job socket not connected", module_id)
            })?;

        let correlation_id = generate_correlation_id();

        // Create pending request entry
        let pending = Arc::new(PendingRequest {
            result: Mutex::new(None),
            ready: Condvar::new(),
        });
        self.pending_requests
            .lock()
            .unwrap()
            .insert(correlation_id.clone(), Arc::clone(&pending));

        // Build and send message: [b"", topic, serialized_message]
        let msg = Message {
            msg_type: "req".to_string(),
            sender: module_id.clone(),
            event: event.to_string(),
            payload,
            recipient: None,
            durability: 1,
            timestamp: None,
            correlation_id: Some(correlation_id.clone()),
        };

        let data = serialize_message(&msg);
        {
            let socket = job_socket.lock().map_err(|e| e.to_string())?;
            socket
                .send_multipart([&b""[..], event.as_bytes(), &data], 0)
                .map_err(|e| e.to_string())?;
        }

        // Wait for response with timeout
        let result = {
            let mut guard = pending.result.lock().unwrap();
            let (g, timeout_result) = pending
                .ready
                .wait_timeout_while(guard, timeout, |result| result.is_none())
                .unwrap();
            guard = g;
            if timeout_result.timed_out() && guard.is_none() {
                self.pending_requests.lock().unwrap().remove(&correlation_id);
                return Err(format!(
                    "Job request '{}' timed out after {:?}",
                    event, timeout
                ));
            }
            guard.take().unwrap_or(serde_json::Value::Null)
        };

        self.pending_requests.lock().unwrap().remove(&correlation_id);
        Ok(result)
    }

    // -----------------------------------------------------------------------
    // Registration
    // -----------------------------------------------------------------------

    fn register(&self) -> Result<bool, String> {
        let ctx = self
            .context
            .lock()
            .unwrap()
            .as_ref()
            .unwrap()
            .clone();

        let sock = ctx.socket(zmq::REQ).map_err(|e| e.to_string())?;
        sock.set_linger(0).map_err(|e| e.to_string())?;
        sock
            .set_rcvtimeo(5000)
            .map_err(|e| e.to_string())?;
        sock.connect(&self.engine_endpoint).map_err(|e| e.to_string())?;

        // Build interfaces data
        let interfaces_data: Vec<serde_json::Value> = self
            .interfaces
            .iter()
            .map(|iface| {
                let mut map = serde_json::Map::new();
                map.insert(
                    "name".to_string(),
                    serde_json::Value::String(iface.name.clone()),
                );
                map.insert(
                    "pattern".to_string(),
                    serde_json::Value::String(iface.pattern.clone()),
                );
                map.insert(
                    "event_type".to_string(),
                    serde_json::Value::String(iface.event_type.clone()),
                );
                map.insert(
                    "durability".to_string(),
                    serde_json::Value::Number(iface.durability.into()),
                );
                serde_json::Value::Object(map)
            })
            .collect();

        let mut payload = serde_json::Map::new();
        payload.insert(
            "family_name".to_string(),
            serde_json::Value::String(self.family_name.clone()),
        );
        payload.insert(
            "interfaces".to_string(),
            serde_json::Value::Array(interfaces_data),
        );
        payload.insert(
            "metadata".to_string(),
            serde_json::Value::Object(serde_json::Map::new()),
        );

        let msg = Message {
            msg_type: "reg".to_string(),
            sender: self.family_name.clone(),
            event: "register".to_string(),
            payload: serde_json::Value::Object(payload),
            recipient: None,
            durability: 1,
            timestamp: None,
            correlation_id: None,
        };

        let data = serialize_message(&msg);
        sock.send(&data, 0).map_err(|e| e.to_string())?;

        let reply_data = sock.recv_bytes(0).map_err(|e| e.to_string())?;
        drop(sock);

        let reply = deserialize_message(&reply_data).map_err(|e| e.to_string())?;

        if reply.msg_type == "ack" {
            if let serde_json::Value::Object(ref ack_payload) = reply.payload {
                // Extract engine-assigned module_id
                if let Some(assigned_id) = ack_payload
                    .get("module_id")
                    .and_then(|v| v.as_str())
                {
                    *self.module_id.lock().unwrap() = assigned_id.to_string();
                }

                let pub_port = ack_payload
                    .get("event_pub_port")
                    .and_then(|v| v.as_u64())
                    .map(|v| v as u16);
                let sub_port = ack_payload
                    .get("event_sub_port")
                    .and_then(|v| v.as_u64())
                    .map(|v| v as u16);
                let job_port = ack_payload
                    .get("job_port")
                    .and_then(|v| v.as_u64())
                    .map(|v| v as u16);

                *self.engine_pub_port.lock().unwrap() = pub_port;
                *self.engine_sub_port.lock().unwrap() = sub_port;
                *self.engine_job_port.lock().unwrap() = job_port;
                self.registered.store(true, Ordering::Relaxed);

                Ok(true)
            } else {
                Ok(false)
            }
        } else {
            Ok(false)
        }
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn extract_host(endpoint: &str) -> &str {
    endpoint
        .strip_prefix("tcp://")
        .and_then(|s| s.rsplit_once(':'))
        .map(|(h, _)| h)
        .unwrap_or("127.0.0.1")
}

fn generate_correlation_id() -> String {
    use rand::Rng;
    let mut rng = rand::thread_rng();
    let mut hex_block = |n: usize| -> String {
        (0..n).map(|_| format!("{:x}", rng.gen_range(0..16))).collect()
    };
    format!(
        "{}-{}-{}-{}-{}",
        hex_block(8),
        hex_block(4),
        hex_block(4),
        hex_block(4),
        hex_block(12),
    )
}

// ---------------------------------------------------------------------------
// Worker threads
// ---------------------------------------------------------------------------

fn event_receiver_loop(
    sub_socket: Arc<Mutex<zmq::Socket>>,
    module_id: String,
    stop_rx: mpsc::Receiver<()>,
    dispatcher: Arc<dyn Fn(&str, &Message) + Send + Sync>,
) {
    loop {
        match stop_rx.try_recv() {
            Ok(()) | Err(mpsc::TryRecvError::Disconnected) => break,
            Err(mpsc::TryRecvError::Empty) => {}
        }

        let socket = sub_socket.lock().unwrap();
        match socket.recv_multipart(0) {
            Ok(frames) => {
                drop(socket);

                if frames.len() >= 2 {
                    let topic = String::from_utf8_lossy(&frames[0]).to_string();
                    match deserialize_message(&frames[1]) {
                        Ok(msg) => {
                            if msg.sender == module_id {
                                continue;
                            }
                            dispatcher(&topic, &msg);
                        }
                        Err(e) => {
                            eprintln!("[{}] Deserialization failed: {}", module_id, e);
                        }
                    }
                }
            }
            Err(zmq::Error::EAGAIN) => continue,
            Err(e) => {
                eprintln!("[{}] Event receive error: {}", module_id, e);
                break;
            }
        }
    }
}

fn heartbeat_loop(
    hb_socket: Arc<Mutex<zmq::Socket>>,
    module_id: String,
    stop_rx: mpsc::Receiver<()>,
) {
    loop {
        match stop_rx.recv_timeout(Duration::from_secs_f64(HEARTBEAT_INTERVAL)) {
            Ok(()) | Err(mpsc::RecvTimeoutError::Disconnected) => break,
            Err(mpsc::RecvTimeoutError::Timeout) => {}
        }

        let mut payload = serde_json::Map::new();
        payload.insert(
            "status".to_string(),
            serde_json::Value::String("alive".to_string()),
        );

        let msg = Message {
            msg_type: "hbt".to_string(),
            sender: module_id.clone(),
            event: "heartbeat".to_string(),
            payload: serde_json::Value::Object(payload),
            recipient: None,
            durability: 1,
            timestamp: None,
            correlation_id: None,
        };

        let socket = hb_socket.lock().unwrap();
        let data = serialize_message(&msg);
        if let Err(e) = socket.send(&data, 0) {
            eprintln!("[{}] Heartbeat send error: {}", module_id, e);
        }
    }
}

fn job_receiver_loop(
    job_socket: Arc<Mutex<zmq::Socket>>,
    module_id: String,
    stop_rx: mpsc::Receiver<()>,
    job_handlers: HashMap<String, Arc<dyn Fn(&Payload) -> Payload + Send + Sync>>,
    pending_requests: Arc<Mutex<HashMap<String, Arc<PendingRequest>>>>,
) {
    loop {
        match stop_rx.try_recv() {
            Ok(()) | Err(mpsc::TryRecvError::Disconnected) => break,
            Err(mpsc::TryRecvError::Empty) => {}
        }

        let socket = job_socket.lock().unwrap();
        match socket.recv_multipart(0) {
            Ok(frames) => {
                drop(socket);

                if frames.len() < 3 {
                    continue;
                }

                // Frames: [b"", topic, message]
                let message_frame = &frames[2];
                let topic = String::from_utf8_lossy(&frames[1]).to_string();

                match deserialize_message(message_frame) {
                    Ok(msg) => {
                        if msg.msg_type == "req" {
                            // Incoming job assignment - dispatch to handler
                            handle_job_request(
                                &job_socket,
                                &module_id,
                                &msg,
                                &job_handlers,
                            );
                        } else if msg.msg_type == "resp" {
                            // Response to our outgoing request
                            handle_job_response(&msg, &pending_requests);
                        }
                    }
                    Err(e) => {
                        eprintln!(
                            "[{}] Job deserialization failed on topic={}: {}",
                            module_id, topic, e
                        );
                    }
                }
            }
            Err(zmq::Error::EAGAIN) => continue,
            Err(e) => {
                eprintln!("[{}] Job receive error: {}", module_id, e);
                break;
            }
        }
    }
}

fn handle_job_request(
    job_socket: &Arc<Mutex<zmq::Socket>>,
    module_id: &str,
    msg: &Message,
    job_handlers: &HashMap<String, Arc<dyn Fn(&Payload) -> Payload + Send + Sync>>,
) {
    let response_payload = if let Some(handler) = job_handlers.get(&msg.event) {
        match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| handler(&msg.payload))) {
            Ok(result) => {
                let mut map = serde_json::Map::new();
                map.insert("result".to_string(), result);
                serde_json::Value::Object(map)
            }
            Err(_) => {
                let mut map = serde_json::Map::new();
                map.insert(
                    "error".to_string(),
                    serde_json::Value::String("Handler panicked".to_string()),
                );
                serde_json::Value::Object(map)
            }
        }
    } else {
        let mut map = serde_json::Map::new();
        map.insert(
            "error".to_string(),
            serde_json::Value::String(format!("No handler for job '{}'", msg.event)),
        );
        serde_json::Value::Object(map)
    };

    let response = Message {
        msg_type: "resp".to_string(),
        sender: module_id.to_string(),
        event: msg.event.clone(),
        payload: response_payload,
        recipient: None,
        durability: 1,
        timestamp: None,
        correlation_id: msg.correlation_id.clone(),
    };

    let data = serialize_message(&response);
    if let Ok(socket) = job_socket.lock() {
        let _ = socket.send_multipart([&b""[..], msg.event.as_bytes(), &data], 0);
    }
}

fn handle_job_response(
    msg: &Message,
    pending_requests: &Arc<Mutex<HashMap<String, Arc<PendingRequest>>>>,
) {
    if let Some(ref correlation_id) = msg.correlation_id {
        let pending = pending_requests.lock().unwrap();
        if let Some(req) = pending.get(correlation_id) {
            *req.result.lock().unwrap() = Some(msg.payload.clone());
            req.ready.notify_all();
        }
    }
}
