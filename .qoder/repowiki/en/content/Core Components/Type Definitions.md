# Type Definitions

<cite>
**Referenced Files in This Document**
- [types.py](file://src/tyche/types.py)
- [message.py](file://src/tyche/message.py)
- [engine.py](file://src/tyche/engine.py)
- [module.py](file://src/tyche/module.py)
- [module_base.py](file://src/tyche/module_base.py)
- [heartbeat.py](file://src/tyche/heartbeat.py)
- [test_types.py](file://tests/unit/test_types.py)
- [example_module.py](file://src/tyche/example_module.py)
</cite>

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Dependency Analysis](#dependency-analysis)
7. [Performance Considerations](#performance-considerations)
8. [Troubleshooting Guide](#troubleshooting-guide)
9. [Conclusion](#conclusion)

## Introduction
This document provides comprehensive coverage of the Tyche Engine's type definitions and data structures. It explains the core data types Endpoint, ModuleInfo, Interface, InterfacePattern, MessageType, DurabilityLevel, and Envelope, along with their enumeration types and values. It documents data validation rules, usage patterns throughout the system, relationships between types, type safety benefits, serialization considerations, backward compatibility requirements, type conversion utilities, validation functions, and error handling for invalid type values.

## Project Structure
The type system is defined centrally and consumed across the engine and module components:
- Core type definitions live in a single module for centralized control
- Message serialization/deserialization uses these types
- Engine and modules consume these types for registration, routing, and heartbeat management
- Tests validate type semantics and defaults

```mermaid
graph TB
Types["types.py<br/>Core type definitions"]
Message["message.py<br/>Message and Envelope<br/>serialization"]
Engine["engine.py<br/>TycheEngine<br/>registration, routing, heartbeat"]
Module["module.py<br/>TycheModule<br/>registration, event handling"]
ModuleBase["module_base.py<br/>ModuleBase<br/>interface discovery"]
Heartbeat["heartbeat.py<br/>HeartbeatManager<br/>liveness tracking"]
Types --> Message
Types --> Engine
Types --> Module
Types --> ModuleBase
Types --> Heartbeat
Message --> Engine
Message --> Module
```

**Diagram sources**
- [types.py:1-102](file://src/tyche/types.py#L1-L102)
- [message.py:1-168](file://src/tyche/message.py#L1-L168)
- [engine.py:1-350](file://src/tyche/engine.py#L1-L350)
- [module.py:1-401](file://src/tyche/module.py#L1-L401)
- [module_base.py:1-120](file://src/tyche/module_base.py#L1-L120)
- [heartbeat.py:1-142](file://src/tyche/heartbeat.py#L1-L142)

**Section sources**
- [types.py:1-102](file://src/tyche/types.py#L1-L102)
- [message.py:1-168](file://src/tyche/message.py#L1-L168)
- [engine.py:1-350](file://src/tyche/engine.py#L1-L350)
- [module.py:1-401](file://src/tyche/module.py#L1-L401)
- [module_base.py:1-120](file://src/tyche/module_base.py#L1-L120)
- [heartbeat.py:1-142](file://src/tyche/heartbeat.py#L1-L142)

## Core Components
This section documents each core type and its role in the system.

### Endpoint
- Purpose: Network endpoint configuration with host and port
- String representation: "tcp://{host}:{port}" for ZeroMQ connectivity
- Usage: Engine registration, event proxy, heartbeat endpoints
- Validation: Host must be a valid IP or hostname; port must be an integer in the valid range

**Section sources**
- [types.py:76-84](file://src/tyche/types.py#L76-L84)
- [engine.py:34-54](file://src/tyche/engine.py#L34-L54)
- [module.py:41-53](file://src/tyche/module.py#L41-L53)

### ModuleInfo
- Purpose: Module registration information passed between modules and the engine
- Fields: module_id, endpoint, interfaces, metadata
- Usage: Engine maintains registry keyed by module_id; used for routing and heartbeat management

**Section sources**
- [types.py:95-102](file://src/tyche/types.py#L95-L102)
- [engine.py:178-198](file://src/tyche/engine.py#L178-L198)
- [engine.py:200-234](file://src/tyche/engine.py#L200-L234)

### Interface
- Purpose: Defines a module's capability to handle events
- Fields: name, pattern, event_type, durability
- Defaults: durability defaults to ASYNC_FLUSH
- Usage: Modules declare interfaces; engine routes events to matching interfaces

**Section sources**
- [types.py:86-93](file://src/tyche/types.py#L86-L93)
- [module_base.py:48-84](file://src/tyche/module_base.py#L48-L84)
- [module.py:87-111](file://src/tyche/module.py#L87-L111)
- [engine.py:183-191](file://src/tyche/engine.py#L183-L191)

### InterfacePattern
- Enumeration values:
  - ON: "on_" — fire-and-forget, load-balanced
  - ACK: "ack_" — must reply with ACK
  - WHISPER: "whisper_" — direct P2P
  - ON_COMMON: "on_common_" — broadcast to all
  - BROADCAST: "broadcast_" — publish via engine
- Usage: Determines handler invocation semantics and subscription patterns

**Section sources**
- [types.py:51-58](file://src/tyche/types.py#L51-L58)
- [module_base.py:74-84](file://src/tyche/module_base.py#L74-L84)
- [module.py:258-264](file://src/tyche/module.py#L258-L264)
- [example_module.py:19-167](file://src/tyche/example_module.py#L19-L167)

### MessageType
- Enumeration values:
  - COMMAND: "cmd"
  - EVENT: "evt"
  - HEARTBEAT: "hbt"
  - REGISTER: "reg"
  - ACK: "ack"
- Usage: Distinguishes message categories across serialization, routing, and workers

**Section sources**
- [types.py:67-74](file://src/tyche/types.py#L67-L74)
- [message.py:13-35](file://src/tyche/message.py#L13-L35)
- [engine.py:158-173](file://src/tyche/engine.py#L158-L173)
- [engine.py:291-297](file://src/tyche/engine.py#L291-L297)
- [module.py:224-245](file://src/tyche/module.py#L224-L245)
- [module.py:358-368](file://src/tyche/module.py#L358-L368)

### DurabilityLevel
- Enumeration values:
  - BEST_EFFORT: 0 — no persistence guarantee
  - ASYNC_FLUSH: 1 — async write (default)
  - SYNC_FLUSH: 2 — sync write, confirmed
- Usage: Controls event persistence behavior; defaults to ASYNC_FLUSH for Interface and Message

**Section sources**
- [types.py:60-65](file://src/tyche/types.py#L60-L65)
- [types.py:92](file://src/tyche/types.py#L92)
- [message.py:32](file://src/tyche/message.py#L32)
- [engine.py:188](file://src/tyche/engine.py#L188)
- [message.py:108](file://src/tyche/message.py#L108)

### Envelope
- Purpose: ZeroMQ routing envelope for messages
- Fields: identity, message, routing_stack
- Usage: Serialization/deserialization of multipart frames for ROUTER/DEALER patterns

**Section sources**
- [message.py:37-49](file://src/tyche/message.py#L37-L49)
- [message.py:114-137](file://src/tyche/message.py#L114-L137)
- [message.py:140-167](file://src/tyche/message.py#L140-L167)

### ModuleId
- Purpose: Module identifier generator with format "{deity}{6-char MD5}"
- Constants: DEITIES list of Greek deities
- Usage: Generates unique module IDs; used in module registration and heartbeat messages

**Section sources**
- [types.py:14-39](file://src/tyche/types.py#L14-L39)
- [module.py:49](file://src/tyche/module.py#L49)
- [example_module.py:40](file://src/tyche/example_module.py#L40)

## Architecture Overview
The type system underpins message routing, module registration, and heartbeat management across the engine and modules.

```mermaid
sequenceDiagram
participant Module as "TycheModule"
participant Engine as "TycheEngine"
participant Router as "ZMQ ROUTER"
participant XPubSub as "XPUB/XSUB Proxy"
participant HB as "HeartbeatManager"
Module->>Engine : "REGISTER Message (MessageType.REGISTER)"
Engine->>Engine : "_create_module_info() validates and constructs ModuleInfo"
Engine->>Router : "send_multipart(serialize(Ack))"
Router-->>Module : "Ack payload with ports"
Module->>XPubSub : "SUBSCRIBE to event topics"
Module->>Engine : "EVENT Message (MessageType.EVENT)"
Engine->>XPubSub : "Forward via proxy"
Module->>Engine : "HEARTBEAT Message (MessageType.HEARTBEAT)"
Engine->>HB : "update(sender)"
```

**Diagram sources**
- [module.py:200-254](file://src/tyche/module.py#L200-L254)
- [engine.py:144-177](file://src/tyche/engine.py#L144-L177)
- [engine.py:178-198](file://src/tyche/engine.py#L178-L198)
- [engine.py:238-277](file://src/tyche/engine.py#L238-L277)
- [heartbeat.py:91-142](file://src/tyche/heartbeat.py#L91-L142)

## Detailed Component Analysis

### Type Safety Benefits
- Enumerations enforce valid values at compile-time and runtime:
  - InterfacePattern ensures only predefined patterns are used
  - MessageType ensures consistent message categorization
  - DurabilityLevel enforces persistence semantics
- Dataclasses provide structural guarantees and default values
- Serialization functions convert enums to their underlying values for transport

**Section sources**
- [types.py:51-74](file://src/tyche/types.py#L51-L74)
- [types.py:86-102](file://src/tyche/types.py#L86-L102)
- [message.py:69-112](file://src/tyche/message.py#L69-L112)

### Serialization Considerations
- MessagePack encoding converts enums to their values and handles Decimal serialization
- Decoding reconstructs enums from their values
- Envelope serialization supports ZeroMQ routing stacks and identity frames

```mermaid
flowchart TD
Start(["Serialize Message"]) --> BuildMap["Build dict with enum values"]
BuildMap --> Encode["msgpack.packb(default=_encode_decimal)"]
Encode --> Bytes["bytes"]
Bytes --> Send["Send over ZeroMQ"]
Receive(["Receive bytes"]) --> Decode["msgpack.unpackb(object_hook=_decode_decimal)"]
Decode --> Reconstruct["Reconstruct Message with enums"]
Reconstruct --> End(["Message ready"])
```

**Diagram sources**
- [message.py:69-112](file://src/tyche/message.py#L69-L112)
- [message.py:51-67](file://src/tyche/message.py#L51-L67)

**Section sources**
- [message.py:13-35](file://src/tyche/message.py#L13-L35)
- [message.py:69-112](file://src/tyche/message.py#L69-L112)
- [message.py:114-167](file://src/tyche/message.py#L114-L167)

### Backward Compatibility Requirements
- Enum values are string or integer codes suitable for long-term storage and interop
- Defaults in dataclasses ensure new fields do not break existing code
- Serialization preserves enum semantics across versions

**Section sources**
- [types.py:60-74](file://src/tyche/types.py#L60-L74)
- [types.py:92](file://src/tyche/types.py#L92)
- [message.py:102-111](file://src/tyche/message.py#L102-L111)

### Type Conversion Utilities
- Enum construction from values:
  - InterfacePattern(...) and DurabilityLevel(...) in engine registration
  - MessageType(...) in deserialization
- String conversion:
  - Endpoint.__str__() produces ZeroMQ-compatible addresses
- Numeric conversion:
  - DurabilityLevel values are integers for persistence semantics

**Section sources**
- [engine.py:186-188](file://src/tyche/engine.py#L186-L188)
- [message.py:103-108](file://src/tyche/message.py#L103-L108)
- [types.py:82-83](file://src/tyche/types.py#L82-L83)

### Validation Functions and Error Handling
- ModuleId generation validates suffix length and hexadecimal format
- Endpoint string representation ensures proper address format
- Interface defaults durability to ASYNC_FLUSH
- Engine registration validates message structure and responds with ACK
- Heartbeat manager tracks liveness and expires stale modules

**Section sources**
- [test_types.py:17-45](file://tests/unit/test_types.py#L17-L45)
- [test_types.py:47-51](file://tests/unit/test_types.py#L47-L51)
- [test_types.py:88-96](file://tests/unit/test_types.py#L88-L96)
- [engine.py:144-177](file://src/tyche/engine.py#L144-L177)
- [heartbeat.py:125-133](file://src/tyche/heartbeat.py#L125-L133)

### Practical Usage Patterns

#### Module Registration
- Modules construct Interface definitions and send MessageType.REGISTER
- Engine deserializes, validates, and constructs ModuleInfo
- Engine replies with MessageType.ACK containing event ports

```mermaid
sequenceDiagram
participant M as "TycheModule"
participant E as "TycheEngine"
M->>E : "REGISTER with interfaces"
E->>E : "deserialize -> _create_module_info"
E-->>M : "ACK with event_pub_port, event_sub_port"
```

**Diagram sources**
- [module.py:200-254](file://src/tyche/module.py#L200-L254)
- [engine.py:144-198](file://src/tyche/engine.py#L144-L198)

**Section sources**
- [module.py:214-233](file://src/tyche/module.py#L214-L233)
- [engine.py:178-198](file://src/tyche/engine.py#L178-L198)

#### Interface Definition and Discovery
- Explicitly add interfaces with add_interface
- Auto-discover interfaces from method names using ModuleBase.discover_interfaces
- Pattern detection determines InterfacePattern from method names

**Section sources**
- [module.py:87-111](file://src/tyche/module.py#L87-L111)
- [module_base.py:48-84](file://src/tyche/module_base.py#L48-L84)
- [example_module.py:58-79](file://src/tyche/example_module.py#L58-L79)

#### Message Handling
- Modules send MessageType.EVENT for fire-and-forget events
- Modules send MessageType.COMMAND for request-response via ack_ patterns
- Engine forwards events via XPUB/XSUB proxy

**Section sources**
- [module.py:301-330](file://src/tyche/module.py#L301-L330)
- [module.py:331-373](file://src/tyche/module.py#L331-L373)
- [engine.py:238-277](file://src/tyche/engine.py#L238-L277)

#### Heartbeat Monitoring
- Modules periodically send MessageType.HEARTBEAT
- Engine updates HeartbeatManager; expired modules are unregistered

**Section sources**
- [module.py:376-401](file://src/tyche/module.py#L376-L401)
- [engine.py:281-349](file://src/tyche/engine.py#L281-L349)
- [heartbeat.py:91-142](file://src/tyche/heartbeat.py#L91-L142)

## Dependency Analysis
The type system forms the foundation for cross-module communication and engine coordination.

```mermaid
classDiagram
class Endpoint {
+string host
+int port
+__str__() string
}
class ModuleInfo {
+string module_id
+Endpoint endpoint
+Interface[] interfaces
+Dict metadata
}
class Interface {
+string name
+InterfacePattern pattern
+string event_type
+DurabilityLevel durability
}
class InterfacePattern {
<<enumeration>>
+ON
+ACK
+WHISPER
+ON_COMMON
+BROADCAST
}
class MessageType {
<<enumeration>>
+COMMAND
+EVENT
+HEARTBEAT
+REGISTER
+ACK
}
class DurabilityLevel {
<<enumeration>>
+BEST_EFFORT
+ASYNC_FLUSH
+SYNC_FLUSH
}
class Envelope {
+bytes identity
+Message message
+bytes[] routing_stack
}
class ModuleId {
+generate(deity) string
}
ModuleInfo --> Endpoint : "has"
ModuleInfo --> Interface : "has many"
Interface --> InterfacePattern : "uses"
Interface --> DurabilityLevel : "uses"
Envelope --> Message : "wraps"
ModuleId --> ModuleInfo : "generates"
```

**Diagram sources**
- [types.py:76-102](file://src/tyche/types.py#L76-L102)
- [message.py:13-49](file://src/tyche/message.py#L13-L49)

**Section sources**
- [types.py:14-102](file://src/tyche/types.py#L14-L102)
- [message.py:13-49](file://src/tyche/message.py#L13-L49)

## Performance Considerations
- Enum serialization is efficient and compact for network transport
- Dataclass fields enable fast attribute access and minimal overhead
- DurabilityLevel controls persistence cost; ASYNC_FLUSH balances throughput and reliability
- ZeroMQ routing envelopes minimize copying for message delivery

## Troubleshooting Guide
Common issues and resolutions:
- Invalid InterfacePattern values: Ensure method names match supported patterns (on_, ack_, whisper_, on_common_)
- DurabilityLevel misuse: Choose appropriate level based on reliability requirements
- Endpoint format errors: Verify host and port values; use Endpoint.__str__() for consistent formatting
- Registration failures: Confirm MessageType.REGISTER payload includes required fields and engine ACK response
- Heartbeat expiration: Check module heartbeat intervals and engine liveness thresholds

**Section sources**
- [module_base.py:74-84](file://src/tyche/module_base.py#L74-L84)
- [engine.py:144-177](file://src/tyche/engine.py#L144-L177)
- [heartbeat.py:125-133](file://src/tyche/heartbeat.py#L125-L133)

## Conclusion
The Tyche Engine's type system provides strong type safety, clear semantics, and robust serialization for distributed event-driven systems. Enumerations and dataclasses ensure correctness and maintainability, while serialization utilities and validation functions support reliable inter-module communication. The documented patterns enable consistent module registration, interface definition, and message handling across the system.