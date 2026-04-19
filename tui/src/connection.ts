import { Subscriber, Request } from "zeromq";
import { encode, decode } from "@msgpack/msgpack";
import {
  ConnectionConfig,
  DEFAULT_CONFIG,
  ConnectionState,
  EventEntry,
  EngineStatus,
  ModuleInfo,
  HealthStatus,
} from "./types.js";

export class ConnectionManager {
  private config: ConnectionConfig;
  private eventSub: Subscriber | null = null;
  private heartbeatSub: Subscriber | null = null;
  private adminReq: Request | null = null;
  private state: ConnectionState = ConnectionState.DISCONNECTED;
  private onEvent: ((entry: EventEntry) => void) | null = null;
  private onHeartbeat: ((moduleId: string) => void) | null = null;
  private onStateChange: ((state: ConnectionState) => void) | null = null;
  private running: boolean = false;

  constructor(config: Partial<ConnectionConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  private setState(newState: ConnectionState): void {
    if (this.state !== newState) {
      this.state = newState;
      this.onStateChange?.(newState);
    }
  }

  setOnEvent(callback: ((entry: EventEntry) => void) | null): void {
    this.onEvent = callback;
  }

  setOnHeartbeat(callback: ((moduleId: string) => void) | null): void {
    this.onHeartbeat = callback;
  }

  setOnStateChange(callback: ((state: ConnectionState) => void) | null): void {
    this.onStateChange = callback;
  }

  async connect(): Promise<void> {
    try {
      this.setState(ConnectionState.CONNECTING);
      this.running = true;

      // Create event subscriber socket (XPUB on engine side)
      this.eventSub = new Subscriber();
      this.eventSub.connect(`tcp://${this.config.host}:${this.config.eventPort}`);
      this.eventSub.subscribe(""); // Subscribe to all topics

      // Create heartbeat subscriber socket (PUB on engine side)
      this.heartbeatSub = new Subscriber();
      this.heartbeatSub.connect(`tcp://${this.config.host}:${this.config.heartbeatPort}`);
      this.heartbeatSub.subscribe(""); // Subscribe to all heartbeats

      // Create admin request socket (ROUTER on engine side)
      this.adminReq = new Request();
      this.adminReq.connect(`tcp://${this.config.host}:${this.config.adminPort}`);

      this.setState(ConnectionState.CONNECTED);

      // Start receive loops
      this.startEventLoop();
      this.startHeartbeatLoop();
    } catch (error) {
      console.error("Failed to connect:", error);
      this.setState(ConnectionState.DISCONNECTED);
      throw error;
    }
  }

  async disconnect(): Promise<void> {
    this.running = false;

    try {
      if (this.eventSub) {
        await this.eventSub.close();
        this.eventSub = null;
      }
    } catch (error) {
      console.error("Error closing event subscriber:", error);
    }

    try {
      if (this.heartbeatSub) {
        await this.heartbeatSub.close();
        this.heartbeatSub = null;
      }
    } catch (error) {
      console.error("Error closing heartbeat subscriber:", error);
    }

    try {
      if (this.adminReq) {
        await this.adminReq.close();
        this.adminReq = null;
      }
    } catch (error) {
      console.error("Error closing admin request socket:", error);
    }

    this.setState(ConnectionState.DISCONNECTED);
  }

  async queryStatus(): Promise<EngineStatus | null> {
    if (!this.adminReq || this.state !== ConnectionState.CONNECTED) {
      return null;
    }

    try {
      const query = encode("STATUS");
      await this.adminReq.send(query);

      const [response] = await this.adminReq.receive();
      const decoded = decode(response) as Record<string, unknown>;

      return {
        status: String(decoded.status ?? "unknown"),
        uptime: Number(decoded.uptime ?? 0),
        moduleCount: Number(decoded.module_count ?? 0),
        eventCount: Number(decoded.event_count ?? 0),
        registerCount: Number(decoded.register_count ?? 0),
      };
    } catch (error) {
      console.error("Error querying status:", error);
      return null;
    }
  }

  async queryModules(): Promise<ModuleInfo[]> {
    if (!this.adminReq || this.state !== ConnectionState.CONNECTED) {
      return [];
    }

    try {
      const query = encode("MODULES");
      await this.adminReq.send(query);

      const [response] = await this.adminReq.receive();
      const decoded = decode(response) as Record<string, unknown>;
      const modules = decoded.modules as Array<Record<string, unknown>> | undefined;

      if (!Array.isArray(modules)) {
        return [];
      }

      return modules.map((mod) => {
        const liveness = Number(mod.liveness ?? 0);
        let health: HealthStatus;
        if (liveness >= 2) {
          health = HealthStatus.OK;
        } else if (liveness >= 1) {
          health = HealthStatus.WARN;
        } else {
          health = HealthStatus.EXPIRED;
        }

        return {
          moduleId: String(mod.module_id ?? ""),
          interfaces: Array.isArray(mod.interfaces) ? mod.interfaces.map(String) : [],
          health,
          liveness,
          lastSeen: Number(mod.last_seen ?? 0),
        };
      });
    } catch (error) {
      console.error("Error querying modules:", error);
      return [];
    }
  }

  private startEventLoop(): void {
    const loop = async () => {
      if (!this.eventSub) return;

      try {
        for await (const msg of this.eventSub) {
          if (!this.running) break;

          try {
            // SUB socket receives [topic, message] or just [message]
            let data: Uint8Array;
            if (Array.isArray(msg)) {
              // Multi-frame message: topic is first frame, body is second
              data = msg[1] as Uint8Array;
            } else {
              // Single frame message
              data = msg as Uint8Array;
            }

            const decoded = decode(data) as Record<string, unknown>;

            // Parse event type from event name prefix
            const eventName = String(decoded.event ?? "");
            let type: string;
            if (eventName.startsWith("on_common_")) {
              type = "on_common";
            } else if (eventName.startsWith("on_")) {
              type = "on";
            } else if (eventName.startsWith("ack_")) {
              type = "ack";
            } else if (eventName.startsWith("whisper_")) {
              type = "whisper";
            } else if (eventName.startsWith("broadcast_")) {
              type = "broadcast";
            } else {
              type = "unknown";
            }

            const entry: EventEntry = {
              timestamp: Date.now() * 1000,
              event: eventName,
              sender: String(decoded.sender ?? ""),
              recipient: decoded.recipient ? String(decoded.recipient) : undefined,
              type,
              payload: (decoded.payload ?? {}) as Record<string, unknown>,
            };

            this.onEvent?.(entry);
          } catch (error) {
            console.error("Error processing event message:", error);
          }
        }
      } catch (error) {
        if (this.running) {
          console.error("Event loop error:", error);
        }
      }
    };

    loop();
  }

  private startHeartbeatLoop(): void {
    const loop = async () => {
      if (!this.heartbeatSub) return;

      try {
        for await (const msg of this.heartbeatSub) {
          if (!this.running) break;

          try {
            // Heartbeat messages are sent as msgpack-encoded data
            let data: Uint8Array;
            if (Array.isArray(msg)) {
              data = msg[1] as Uint8Array;
            } else {
              data = msg as Uint8Array;
            }

            const decoded = decode(data) as Record<string, unknown>;
            const sender = String(decoded.sender ?? "");

            if (sender) {
              this.onHeartbeat?.(sender);
            }
          } catch (error) {
            console.error("Error processing heartbeat message:", error);
          }
        }
      } catch (error) {
        if (this.running) {
          console.error("Heartbeat loop error:", error);
        }
      }
    };

    loop();
  }
}
