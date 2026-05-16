//! Core type definitions for Tyche Engine.
//!
//! Mirrors the Python `tyche.types` module in Rust.

use rand::Rng;
use serde::{Deserialize, Serialize};

// ---------------------------------------------------------------------------
// Endpoint
// ---------------------------------------------------------------------------

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Endpoint {
    pub host: String,
    pub port: u16,
}

impl Endpoint {
    pub fn new(host: &str, port: u16) -> Self {
        Self {
            host: host.to_string(),
            port,
        }
    }
}

impl std::fmt::Display for Endpoint {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "tcp://{}:{}", self.host, self.port)
    }
}

// ---------------------------------------------------------------------------
// ModuleId
// ---------------------------------------------------------------------------

pub struct ModuleId;

impl ModuleId {
    const DEITIES: &'static [&'static str] = &[
        "zeus", "hera", "poseidon", "hades", "example",
        "apollo", "artemis", "ares", "aphrodite", "hermes",
        "dionysus", "demeter", "hephaestus", "hestia",
    ];

    /// Generate a new module ID in format `{deity}{6-char hex}`.
    pub fn generate(deity: Option<&str>) -> String {
        let mut rng = rand::thread_rng();

        let deity = deity.unwrap_or_else(|| {
            let idx = rng.gen_range(0..Self::DEITIES.len());
            Self::DEITIES[idx]
        });

        let suffix: String = (0..6)
            .map(|_| format!("{:x}", rng.gen_range(0..16)))
            .collect();

        format!("{}{}", deity, suffix)
    }
}

// ---------------------------------------------------------------------------
// Interface
// ---------------------------------------------------------------------------

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Interface {
    pub name: String,
    pub pattern: String,
    pub event_type: String,
    pub durability: i32,
}

// ---------------------------------------------------------------------------
// Message
// ---------------------------------------------------------------------------

pub type Payload = serde_json::Value;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Message {
    #[serde(rename = "msg_type")]
    pub msg_type: String,
    pub sender: String,
    pub event: String,
    pub payload: Payload,
    pub recipient: Option<String>,
    pub durability: i32,
    pub timestamp: Option<f64>,
    #[serde(rename = "correlation_id")]
    pub correlation_id: Option<String>,
}

// ---------------------------------------------------------------------------
// ReceivedEvent
// ---------------------------------------------------------------------------

#[derive(Clone, Debug)]
pub struct ReceivedEvent {
    pub event: String,
    pub payload: Payload,
}

// ---------------------------------------------------------------------------
// Enums (for type-safe APIs)
// ---------------------------------------------------------------------------

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub enum InterfacePattern {
    #[serde(rename = "on")]
    On,
    #[serde(rename = "send")]
    Send,
    #[serde(rename = "handle")]
    Handle,
    #[serde(rename = "request")]
    Request,
}

impl InterfacePattern {
    /// Return the string value matching Python InterfacePattern.value.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::On => "on",
            Self::Send => "send",
            Self::Handle => "handle",
            Self::Request => "request",
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub enum DurabilityLevel {
    #[serde(rename = "best_effort")]
    BestEffort = 0,
    #[serde(rename = "async_flush")]
    AsyncFlush = 1,
    #[serde(rename = "sync_flush")]
    SyncFlush = 2,
}

impl Default for DurabilityLevel {
    fn default() -> Self {
        DurabilityLevel::AsyncFlush
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub enum MessageType {
    #[serde(rename = "cmd")]
    Command,
    #[serde(rename = "evt")]
    Event,
    #[serde(rename = "hbt")]
    Heartbeat,
    #[serde(rename = "reg")]
    Register,
    #[serde(rename = "ack")]
    Ack,
    #[serde(rename = "resp")]
    Response,
    #[serde(rename = "req")]
    Request,
}
