# Communication Patterns

<cite>
**Referenced Files in This Document**
- [engine.py](file://src/tyche/engine.py)
- [module.py](file://src/tyche/module.py)
- [module_base.py](file://src/tyche/module_base.py)
- [message.py](file://src/tyche/message.py)
- [types.py](file://src/tyche/types.py)
- [example_module.py](file://src/tyche/example_module.py)
- [heartbeat.py](file://src/tyche/heartbeat.py)
- [run_engine.py](file://examples/run_engine.py)
- [run_module.py](file://examples/run_module.py)
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
This document explains Tyche Engine’s four primary communication patterns and how ZeroMQ socket patterns implement them:
- Fire-and-forget events (on_*)
- Request-response (ack_*)
- Direct P2P messaging (whisper_*)
- Broadcast events (on_common_*)

It covers ZeroMQ socket types, behavioral characteristics, delivery guarantees, use cases, implementation details, interface naming conventions, message flow diagrams, practical examples, performance implications, failure modes, and best practices.

## Project Structure
Tyche Engine organizes communication around a central broker (engine) and modules that connect to it. The engine exposes:
- Registration endpoint (REQ/REP handshake)
- Event routing via XPUB/XSUB proxy
- Heartbeat monitoring (Paranoid Pirate pattern)
- Acknowledgment channel (optional separate endpoint)

Modules connect using:
- REQ for registration
- PUB/SUB for event exchange
- DEALER for heartbeats

```mermaid
graph TB
subgraph "Tyche Engine"
REG["Registration Endpoint<br/>REQ/REP"]
XPUB["Event XPUB<br/>Publisher"]
XSUB["Event XSUB<br/>Subscriber"]
HB_OUT["Heartbeat PUB<br/>Outbound"]
HB_IN["Heartbeat ROUTER<br/>Inbound"]
MON["Monitor Worker"]
PROXY["Event Proxy Worker<br/>XPUB/XSUB"]
end
subgraph "Tyche Module"
MOD_REQ["Module REQ<br/>Registration"]
MOD_PUB["Module PUB<br/>Events"]
MOD_SUB["Module SUB<br/>Events"]
MOD_DEALER["Module DEALER<br/>Heartbeats"]
end
MOD_REQ --> REG
MOD_PUB --> XSUB
XPUB --> MOD_SUB
MOD_DEALER --> HB_IN
HB_OUT --> MOD_DEALER
PROXY --- XPUB
PROXY --- XSUB
MON --> REG
MON --> HB_IN
```

**Diagram sources**
- [engine.py:121-143](file://src/tyche/engine.py#L121-L143)
- [engine.py:238-277](file://src/tyche/engine.py#L238-L277)
- [engine.py:281-305](file://src/tyche/engine.py#L281-L305)
- [engine.py:307-339](file://src/tyche/engine.py#L307-L339)
- [module.py:200-254](file://src/tyche/module.py#L200-L254)
- [module.py:138-177](file://src/tyche/module.py#L138-L177)
- [module.py:376-400](file://src/tyche/module.py#L376-L400)

**Section sources**
- [engine.py:34-50](file://src/tyche/engine.py#L34-L50)
- [module.py:41-49](file://src/tyche/module.py#L41-L49)

## Core Components
- TycheEngine: Central broker managing registration, event routing, heartbeats, and module lifecycle.
- TycheModule: Base module implementation handling registration, event subscription/publishing, request-response acknowledgments, and heartbeats.
- ModuleBase: Defines interface discovery and naming conventions for the four patterns.
- Message: Serialization/deserialization for ZeroMQ frames and envelopes.
- Types: Enumerations for patterns, message types, durability, and endpoints.

Key responsibilities:
- Registration: REQ socket handshake for module registration and interface discovery.
- Event routing: XPUB/XSUB proxy for pub/sub event distribution.
- Heartbeats: PUB/ROUTER pair implementing Paranoid Pirate liveness checks.
- Messaging: MessagePack serialization and envelope framing for ZeroMQ multipart messages.

**Section sources**
- [engine.py:25-32](file://src/tyche/engine.py#L25-L32)
- [module.py:28-39](file://src/tyche/module.py#L28-L39)
- [module_base.py:10-30](file://src/tyche/module_base.py#L10-L30)
- [message.py:13-35](file://src/tyche/message.py#L13-L35)
- [types.py:51-74](file://src/tyche/types.py#L51-L74)

## Architecture Overview
The engine exposes distinct endpoints for registration, event routing, and heartbeats. Modules connect to these endpoints and participate in the event mesh. The event proxy mirrors XPUB to XSUB frames, enabling fan-out to all subscribers.

```mermaid
sequenceDiagram
participant Mod as "TycheModule"
participant Eng as "TycheEngine"
participant XPUB as "Engine XPUB"
participant XSUB as "Engine XSUB"
participant Sub as "Other Modules"
Mod->>Eng : "REQ registration"
Eng-->>Mod : "ACK with ports"
Mod->>XSUB : "PUB events"
XSUB-->>XPUB : "Forward frames"
XPUB-->>Sub : "SUB events"
Note over Mod,Sub : "Fire-and-forget events distributed via XPUB/XSUB"
```

**Diagram sources**
- [module.py:200-254](file://src/tyche/module.py#L200-L254)
- [engine.py:238-277](file://src/tyche/engine.py#L238-L277)
- [module.py:138-177](file://src/tyche/module.py#L138-L177)

## Detailed Component Analysis

### Fire-and-Forget Events (on_*)
Behavioral characteristics:
- Best-effort delivery with no guaranteed acknowledgment.
- Load-balanced distribution across subscribers.
- Handlers return immediately; no response payload is expected.

ZeroMQ socket pattern:
- Module publishes events via PUB to engine’s XSUB.
- Engine’s event proxy mirrors XPUB to XSUB frames.
- Subscribers receive events via SUB.

Delivery guarantees:
- Best-effort; no persistence or retry.
- FIFO per subscriber; at-least-once semantics via ZeroMQ SUB.

Implementation details:
- Module publishes with topic as event name and serialized message body.
- Engine’s proxy forwards frames unchanged.

Practical example:
- See [example_module.py:80-85](file://src/tyche/example_module.py#L80-L85) for an on_data handler.
- See [module.py:301-329](file://src/tyche/module.py#L301-L329) for send_event implementation.

```mermaid
sequenceDiagram
participant Sender as "TycheModule (Publisher)"
participant XSUB as "Engine XSUB"
participant Proxy as "Engine Proxy"
participant XPUB as "Engine XPUB"
participant Recv as "TycheModule (Subscriber)"
Sender->>XSUB : "PUB frame [topic, message]"
XSUB-->>Proxy : "Forward"
Proxy-->>XPUB : "Mirror frame"
XPUB-->>Recv : "SUB frame [topic, message]"
Recv->>Recv : "Dispatch to handler"
```

**Diagram sources**
- [module.py:301-329](file://src/tyche/module.py#L301-L329)
- [engine.py:238-277](file://src/tyche/engine.py#L238-L277)
- [module.py:265-298](file://src/tyche/module.py#L265-L298)

Best practices:
- Use on_* for telemetry, metrics, and non-critical notifications.
- Keep payloads small and serializable.
- Avoid long-running work inside handlers; offload to background tasks if needed.

Failure modes:
- Network partitions: events may be dropped.
- Subscriber overload: back-pressure via ZeroMQ; consider batching or rate limiting.

**Section sources**
- [module.py:301-329](file://src/tyche/module.py#L301-L329)
- [module.py:265-298](file://src/tyche/module.py#L265-L298)
- [example_module.py:80-85](file://src/tyche/example_module.py#L80-L85)

### Request-Response (ack_*)
Behavioral characteristics:
- Synchronous request with required acknowledgment.
- Module sends a command-like message and waits for a response within a timeout.
- Handlers must return a dictionary payload.

ZeroMQ socket pattern:
- Module uses a temporary REQ socket to send a COMMAND message.
- Engine responds with an ACK message on the same socket.
- Acknowledgment channel is separate from the event proxy.

Delivery guarantees:
- At-least-once delivery to engine; response sent back to requester.
- Timeout-based failure detection.

Implementation details:
- Module.call_ack constructs a COMMAND message and waits for ACK.
- Engine routes COMMAND to registered handlers and replies with ACK.

Practical example:
- See [example_module.py:87-100](file://src/tyche/example_module.py#L87-L100) for an ack_request handler.
- See [module.py:331-373](file://src/tyche/module.py#L331-L373) for call_ack implementation.

```mermaid
sequenceDiagram
participant Caller as "TycheModule (Caller)"
participant Eng as "TycheEngine"
participant Handler as "Handler Module"
participant Reply as "TycheModule (Reply)"
Caller->>Eng : "REQ COMMAND (ack_*)"
Eng->>Handler : "Route to handler"
Handler-->>Eng : "Return payload"
Eng-->>Caller : "ACK payload"
Note over Caller,Reply : "Timeout if no ACK within configured window"
```

**Diagram sources**
- [module.py:331-373](file://src/tyche/module.py#L331-L373)
- [engine.py:144-177](file://src/tyche/engine.py#L144-L177)
- [module_base.py:100-119](file://src/tyche/module_base.py#L100-L119)

Best practices:
- Use ack_* for RPC-like operations requiring confirmation.
- Keep request payloads minimal and idempotent.
- Set reasonable timeouts based on expected handler latency.

Failure modes:
- Handler crash or slow processing: caller receives timeout.
- Network errors: REQ socket may fail; caller should retry or abort.

**Section sources**
- [module.py:331-373](file://src/tyche/module.py#L331-L373)
- [example_module.py:87-100](file://src/tyche/example_module.py#L87-L100)
- [module_base.py:100-119](file://src/tyche/module_base.py#L100-L119)

### Direct P2P Messaging (whisper_*)
Behavioral characteristics:
- Direct, point-to-point communication between two modules.
- Bypasses engine event proxy; uses direct socket paths.
- Naming convention includes target module ID in the handler name.

ZeroMQ socket pattern:
- Whisper handlers are discovered via naming convention (whisper_{target}_{event}).
- Implementation relies on module auto-discovery and handler routing.

Delivery guarantees:
- Best-effort; depends on underlying transport and network conditions.
- No built-in engine routing for whispers; requires sender to know target.

Implementation details:
- ModuleBase discovers whisper interfaces automatically from method names.
- Example module demonstrates a whisper_athena_message handler.

Practical example:
- See [example_module.py:102-113](file://src/tyche/example_module.py#L102-L113) for a whisper handler.
- See [module_base.py:48-84](file://src/tyche/module_base.py#L48-L84) for interface discovery logic.

```mermaid
flowchart TD
Start(["Whisper Invocation"]) --> CheckTarget["Resolve Target Module"]
CheckTarget --> BuildTopic["Build Topic: whisper_{target}_{event}"]
BuildTopic --> Send["Send via Engine Event Channel"]
Send --> Receive["Target Receives on whisper_{target}_{event}"]
Receive --> Dispatch["Dispatch to Handler"]
Dispatch --> End(["Complete"])
```

**Diagram sources**
- [module_base.py:48-84](file://src/tyche/module_base.py#L48-L84)
- [example_module.py:102-113](file://src/tyche/example_module.py#L102-L113)

Best practices:
- Use whisper_* for sensitive or private messages between known modules.
- Ensure target module is registered and subscribed to the topic.
- Keep whisper topics stable and documented.

Failure modes:
- Target module not registered or not subscribed: message lost.
- Network connectivity issues: delivery fails silently.

**Section sources**
- [module_base.py:48-84](file://src/tyche/module_base.py#L48-L84)
- [example_module.py:102-113](file://src/tyche/example_module.py#L102-L113)

### Broadcast Events (on_common_*)
Behavioral characteristics:
- Broadcast to all subscribers of the event.
- Fan-out across all modules subscribed to the topic.
- Useful for announcements, global updates, and coordination signals.

ZeroMQ socket pattern:
- Module publishes on_common_* events via PUB to engine’s XSUB.
- Engine’s proxy mirrors frames to all subscribers via XPUB.
- All modules subscribed to the topic receive the broadcast.

Delivery guarantees:
- Best-effort broadcast; no per-subscriber acknowledgment.
- All subscribers receive the message.

Implementation details:
- Example module demonstrates on_common_ping/pong handlers that schedule subsequent broadcasts.
- Module subscribes to topics matching its handler names.

Practical example:
- See [example_module.py:115-122](file://src/tyche/example_module.py#L115-L122) for on_common_broadcast.
- See [example_module.py:124-150](file://src/tyche/example_module.py#L124-L150) for on_common_ping/pong with scheduled broadcasts.
- See [module.py:258-264](file://src/tyche/module.py#L258-L264) for subscription setup.

```mermaid
sequenceDiagram
participant Sender as "TycheModule (Publisher)"
participant XSUB as "Engine XSUB"
participant Proxy as "Engine Proxy"
participant XPUB as "Engine XPUB"
participant Sub1 as "Subscriber Module 1"
participant Sub2 as "Subscriber Module 2"
Sender->>XSUB : "PUB frame [on_common_ping, message]"
XSUB-->>Proxy : "Forward"
Proxy-->>XPUB : "Mirror frame"
XPUB-->>Sub1 : "SUB frame [on_common_ping, message]"
XPUB-->>Sub2 : "SUB frame [on_common_ping, message]"
Sub1->>Sub1 : "Dispatch to on_common_ping"
Sub2->>Sub2 : "Dispatch to on_common_ping"
```

**Diagram sources**
- [module.py:301-329](file://src/tyche/module.py#L301-L329)
- [engine.py:238-277](file://src/tyche/engine.py#L238-L277)
- [module.py:258-264](file://src/tyche/module.py#L258-L264)
- [example_module.py:124-150](file://src/tyche/example_module.py#L124-L150)

Best practices:
- Use on_common_* for global announcements and coordination.
- Avoid heavy payloads; keep broadcasts lightweight.
- Coordinate timing to prevent thundering herds of responses.

Failure modes:
- Network partitions: some subscribers miss broadcasts.
- Subscriber overload: back-pressure via ZeroMQ; consider throttling.

**Section sources**
- [example_module.py:115-122](file://src/tyche/example_module.py#L115-L122)
- [example_module.py:124-150](file://src/tyche/example_module.py#L124-L150)
- [module.py:258-264](file://src/tyche/module.py#L258-L264)

## Dependency Analysis
The communication patterns rely on:
- Interface naming conventions defined in ModuleBase.
- Message types and durability levels defined in Types.
- Serialization/deserialization in Message.
- Engine workers for registration, event proxy, and heartbeats.
- Module workers for registration, event handling, and heartbeats.

```mermaid
graph LR
MB["ModuleBase<br/>Interface Discovery"] --> TP["Types<br/>InterfacePattern, MessageType"]
MB --> MSG["Message<br/>Serialization"]
MB --> MOD["TycheModule<br/>Handlers & Sockets"]
MOD --> ENG["TycheEngine<br/>Workers"]
ENG --> HB["Heartbeat<br/>Paranoid Pirate"]
MOD --> EX["ExampleModule<br/>Patterns"]
```

**Diagram sources**
- [module_base.py:48-84](file://src/tyche/module_base.py#L48-L84)
- [types.py:51-74](file://src/tyche/types.py#L51-L74)
- [message.py:69-111](file://src/tyche/message.py#L69-L111)
- [module.py:28-39](file://src/tyche/module.py#L28-L39)
- [engine.py:25-32](file://src/tyche/engine.py#L25-L32)
- [heartbeat.py:91-142](file://src/tyche/heartbeat.py#L91-L142)
- [example_module.py:19-31](file://src/tyche/example_module.py#L19-L31)

**Section sources**
- [module_base.py:48-84](file://src/tyche/module_base.py#L48-L84)
- [types.py:51-74](file://src/tyche/types.py#L51-L74)
- [message.py:69-111](file://src/tyche/message.py#L69-L111)
- [module.py:28-39](file://src/tyche/module.py#L28-L39)
- [engine.py:25-32](file://src/tyche/engine.py#L25-L32)
- [heartbeat.py:91-142](file://src/tyche/heartbeat.py#L91-L142)
- [example_module.py:19-31](file://src/tyche/example_module.py#L19-L31)

## Performance Considerations
- Fire-and-forget (on_*): Minimal overhead; PUB/SUB fan-out scales with subscribers. Tune subscription granularity to reduce unnecessary traffic.
- Request-response (ack_*): Adds latency due to round-trip and serialization. Use timeouts to bound wait time; consider batching requests if feasible.
- Direct P2P (whisper_*): Best-effort delivery; overhead equals standard event publishing. Favor whisper for sensitive or targeted messages.
- Broadcast (on_common_*): Fan-out cost increases with subscriber count. Limit payload size and frequency; stagger broadcasts to avoid spikes.

Failure modes and mitigations:
- Registration timeouts: increase RCVTIMEO or retry registration.
- Event proxy stalls: monitor poller and restart worker if needed.
- Heartbeat liveness: Paranoid Pirate pattern detects dead modules; engine unregisters expired modules.

Best practices:
- Use durability levels judiciously; best effort is sufficient for most telemetry.
- Keep payloads small and serializable; leverage MessagePack encoding.
- Monitor throughput and latency; adjust subscription filters and broadcast cadence.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and resolutions:
- Registration failures: Verify endpoints and network connectivity; check engine logs for deserialization errors.
- No events received: Confirm subscription topics match handler names; ensure engine proxy is running.
- Acknowledgment timeouts: Increase timeout or optimize handler performance; verify engine routing for COMMAND/ACK.
- Heartbeat anomalies: Check DEALER/PUB socket bindings; ensure heartbeat intervals align across modules.

Operational tips:
- Use example scripts to validate engine and module connectivity.
- Inspect module interface discovery and handler routing.
- Monitor engine worker threads and socket states.

**Section sources**
- [module.py:200-254](file://src/tyche/module.py#L200-L254)
- [engine.py:238-277](file://src/tyche/engine.py#L238-L277)
- [module.py:331-373](file://src/tyche/module.py#L331-L373)
- [heartbeat.py:91-142](file://src/tyche/heartbeat.py#L91-L142)
- [run_engine.py:27-32](file://examples/run_engine.py#L27-L32)
- [run_module.py:28-31](file://examples/run_module.py#L28-L31)

## Conclusion
Tyche Engine’s communication patterns combine ZeroMQ socket patterns with clear naming conventions to support diverse messaging needs:
- Fire-and-forget for scalable, best-effort distribution.
- Request-response for synchronous confirmations.
- Direct P2P for private, targeted exchanges.
- Broadcast for global coordination.

By leveraging the provided interfaces, serialization, and engine workers, developers can implement robust, high-performance inter-module communication tailored to their use cases.