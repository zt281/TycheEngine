# Tyche Engine 2-Node System - Process Separation Fix

> **CRITICAL FIX:** The current implementation (v1) violates the core distributed architecture by running Engine and Modules in the same process. This plan fixes that.

## Problem Statement

Current implementation:
- ❌ Engine and Module run in same Python process using asyncio
- ❌ No actual process isolation
- ❌ Cannot scale across multiple CPUs/machines

Required architecture:
- ✅ Engine runs as standalone process
- ✅ Each Module runs as separate process
- ✅ Communication via ZeroMQ across process boundaries
- ✅ Can run on different machines

## Corrected Architecture

```
Process A (Node A)              Process B (Node B)
+------------------+            +------------------+
|   TycheEngine    |<---ZMQ--->|   ExampleModule  |
|    __main__      |            |    __main__      |
+------------------+            +------------------+
```

## Files to Create/Modify

### New Entry Point Scripts
| File | Purpose |
|------|---------|
| `src/tyche/engine_main.py` | Standalone engine process entry point |
| `src/tyche/module_main.py` | Standalone module process entry point |
| `examples/run_engine.py` | Example: Start engine process |
| `examples/run_module.py` | Example: Start module process |

### Core Fixes
| File | Fix |
|------|-----|
| `src/tyche/engine.py` | Remove asyncio, use blocking ZMQ with threads for handlers |
| `src/tyche/module.py` | Remove asyncio, use blocking ZMQ with threads |
| `src/tyche/example_module.py` | Make runnable as `if __name__ == "__main__"` |

## Task 1: Create Engine Entry Point

**File:** `src/tyche/engine_main.py`

```python
#!/usr/bin/env python3
"""Standalone TycheEngine process entry point."""

import argparse
import signal
import sys
from tyche.engine import TycheEngine
from tyche.types import Endpoint


def main():
    parser = argparse.ArgumentParser(description='Tyche Engine - Central broker')
    parser.add_argument('--registration-port', type=int, default=5555,
                        help='Port for module registration (ROUTER)')
    parser.add_argument('--event-port', type=int, default=5556,
                        help='Port for event broadcasting (XPUB/XSUB)')
    parser.add_argument('--heartbeat-port', type=int, default=5558,
                        help='Port for heartbeat (PUB)')
    parser.add_argument('--host', default='127.0.0.1',
                        help='Host to bind to')
    
    args = parser.parse_args()
    
    engine = TycheEngine(
        registration_endpoint=Endpoint(args.host, args.registration_port),
        event_endpoint=Endpoint(args.host, args.event_port),
        heartbeat_endpoint=Endpoint(args.host, args.heartbeat_port)
    )
    
    def shutdown(sig, frame):
        print("\nShutting down engine...")
        engine.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    print(f"Starting TycheEngine on {args.host}")
    print(f"  Registration: port {args.registration_port}")
    print(f"  Events: port {args.event_port}")
    print(f"  Heartbeat: port {args.heartbeat_port}")
    
    engine.run()  # Blocking call


if __name__ == "__main__":
    main()
```

## Task 2: Create Module Entry Point

**File:** `src/tyche/module_main.py`

```python
#!/usr/bin/env python3
"""Standalone module process entry point."""

import argparse
import signal
import sys
from tyche.example_module import ExampleModule
from tyche.types import Endpoint


def main():
    parser = argparse.ArgumentParser(description='Tyche Module - Example worker')
    parser.add_argument('--engine-host', default='127.0.0.1',
                        help='Engine host address')
    parser.add_argument('--engine-port', type=int, default=5555,
                        help='Engine registration port')
    parser.add_argument('--module-id', default=None,
                        help='Optional module ID (auto-generated if not provided)')
    
    args = parser.parse_args()
    
    module = ExampleModule(
        engine_endpoint=Endpoint(args.engine_host, args.engine_port),
        module_id=args.module_id
    )
    
    def shutdown(sig, frame):
        print("\nShutting down module...")
        module.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    print(f"Starting module, connecting to engine at {args.engine_host}:{args.engine_port}")
    
    module.run()  # Blocking call


if __name__ == "__main__":
    main()
```

## Task 3: Fix Engine to Use Threading (Not Asyncio)

**Modify:** `src/tyche/engine.py`

Remove `async/await` and use threading:

```python
"""TycheEngine - Central broker using threads for multi-process support."""

import threading
import time
from typing import Dict, List, Optional, Any
import zmq

from tyche.types import (
    Endpoint, ModuleInfo, Interface, InterfacePattern,
    DurabilityLevel, MessageType, HEARTBEAT_INTERVAL, HEARTBEAT_LIVENESS
)
from tyche.message import Message, serialize, deserialize
from tyche.heartbeat import HeartbeatManager


class TycheEngine:
    """Central broker for Tyche Engine - runs in standalone process."""
    
    def __init__(
        self,
        registration_endpoint: Endpoint,
        event_endpoint: Endpoint,
        heartbeat_endpoint: Endpoint,
        ack_endpoint: Optional[Endpoint] = None
    ):
        self.registration_endpoint = registration_endpoint
        self.event_endpoint = event_endpoint
        self.heartbeat_endpoint = heartbeat_endpoint
        self.ack_endpoint = ack_endpoint or Endpoint(
            event_endpoint.host, event_endpoint.port + 10
        )
        
        self.modules: Dict[str, ModuleInfo] = {}
        self.interfaces: Dict[str, List[tuple]] = {}
        self.heartbeat_manager = HeartbeatManager()
        
        self.context: Optional[zmq.Context] = None
        self._running = False
        self._threads: List[threading.Thread] = []
    
    def run(self) -> None:
        """Start the engine - blocks until stop() is called."""
        self.context = zmq.Context()
        self._running = True
        
        # Start worker threads
        self._threads = [
            threading.Thread(target=self._registration_worker, name="registration"),
            threading.Thread(target=self._heartbeat_worker, name="heartbeat"),
            threading.Thread(target=self._monitor_worker, name="monitor"),
        ]
        
        for t in self._threads:
            t.start()
        
        # Block main thread
        try:
            while self._running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
    
    def stop(self) -> None:
        """Stop the engine."""
        self._running = False
        
        for t in self._threads:
            t.join(timeout=2.0)
        
        if self.context:
            self.context.term()
    
    def _registration_worker(self) -> None:
        """Handle module registrations in dedicated thread."""
        socket = self.context.socket(zmq.ROUTER)
        socket.bind(str(self.registration_endpoint))
        socket.setsockopt(zmq.RCVTIMEO, 100)  # 100ms timeout for polling
        
        while self._running:
            try:
                frames = socket.recv_multipart()
                self._process_registration(socket, frames)
            except zmq.error.Again:
                continue  # Timeout, check _running
            except Exception as e:
                print(f"Registration error: {e}")
    
    def _process_registration(self, socket, frames: List[bytes]) -> None:
        """Process registration request."""
        if len(frames) < 3:
            return
        
        identity = frames[0]
        msg_data = frames[2] if frames[1] == b"" else frames[1]
        
        try:
            msg = deserialize(msg_data)
            
            if msg.msg_type == MessageType.REGISTER:
                # Register module
                module_info = self._create_module_info(msg)
                self.register_module(module_info)
                
                # Send ACK
                ack = Message(
                    msg_type=MessageType.ACK,
                    sender="engine",
                    event="register_ack",
                    payload={"status": "ok", "module_id": module_info.module_id}
                )
                socket.send_multipart([identity, serialize(ack)])
                print(f"Registered module: {module_info.module_id}")
                
        except Exception as e:
            print(f"Failed to process registration: {e}")
    
    def _create_module_info(self, msg: Message) -> ModuleInfo:
        """Create ModuleInfo from registration message."""
        from tyche.types import Interface
        
        module_id = msg.payload.get("module_id")
        interfaces_data = msg.payload.get("interfaces", [])
        
        interfaces = [
            Interface(
                name=i["name"],
                pattern=InterfacePattern(i["pattern"]),
                event_type=i.get("event_type", i["name"]),
                durability=DurabilityLevel(i.get("durability", 1))
            )
            for i in interfaces_data
        ]
        
        return ModuleInfo(
            module_id=module_id,
            endpoint=Endpoint("127.0.0.1", 0),  # Will be updated with actual
            interfaces=interfaces,
            metadata=msg.payload.get("metadata", {})
        )
    
    def register_module(self, module_info: ModuleInfo) -> None:
        """Register a module and its interfaces."""
        self.modules[module_info.module_id] = module_info
        
        for interface in module_info.interfaces:
            event_name = interface.name
            if event_name not in self.interfaces:
                self.interfaces[event_name] = []
            self.interfaces[event_name].append(
                (module_info.module_id, interface)
            )
        
        self.heartbeat_manager.register(module_info.module_id)
    
    def unregister_module(self, module_id: str) -> None:
        """Unregister a module."""
        if module_id not in self.modules:
            return
        
        module_info = self.modules[module_id]
        
        for interface in module_info.interfaces:
            event_name = interface.name
            if event_name in self.interfaces:
                self.interfaces[event_name] = [
                    (mid, iface) for mid, iface in self.interfaces[event_name]
                    if mid != module_id
                ]
        
        del self.modules[module_id]
        self.heartbeat_manager.unregister(module_id)
    
    def _heartbeat_worker(self) -> None:
        """Send heartbeat broadcasts."""
        socket = self.context.socket(zmq.PUB)
        socket.bind(str(self.heartbeat_endpoint))
        
        while self._running:
            try:
                # Send heartbeat to all modules
                msg = Message(
                    msg_type=MessageType.HEARTBEAT,
                    sender="engine",
                    event="heartbeat",
                    payload={"timestamp": time.time()}
                )
                socket.send_multipart([b"heartbeat", serialize(msg)])
                time.sleep(HEARTBEAT_INTERVAL)
            except Exception as e:
                print(f"Heartbeat error: {e}")
    
    def _monitor_worker(self) -> None:
        """Monitor peer health."""
        while self._running:
            expired = self.heartbeat_manager.tick_all()
            for module_id in expired:
                print(f"Module {module_id} expired")
                self.unregister_module(module_id)
            
            time.sleep(HEARTBEAT_INTERVAL)
```

## Task 4: Fix Module to Use Threading

**Modify:** `src/tyche/module.py`

Similar changes - remove asyncio, use threading.

## Task 5: Integration Test for Multi-Process

**Create:** `tests/integration/test_multiprocess.py`

Use `subprocess.Popen` to actually run separate processes and verify communication.

## Task 6: Examples Directory

**Create:** `examples/` with runnable examples showing:
1. Start engine in one terminal
2. Start module in another terminal
3. Verify they communicate

## Verification

```bash
# Terminal 1: Start engine
python -m tyche.engine_main --registration-port 5555

# Terminal 2: Start module
python -m tyche.module_main --engine-port 5555

# Expected: Module registers, heartbeats exchanged
```

## Success Criteria

- ✅ Engine can run as standalone process
- ✅ Module can run as standalone process  
- ✅ Multiple modules can connect to one engine
- ✅ Communication works across actual process boundaries
- ✅ Can run engine and modules on different machines
