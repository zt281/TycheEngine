// Connection configuration
export interface ConnectionConfig {
  host: string;
  eventPort: number;
  heartbeatPort: number;
  adminPort: number;
}

export const DEFAULT_CONFIG: ConnectionConfig = {
  host: "127.0.0.1",
  eventPort: 5556,
  heartbeatPort: 5558,
  adminPort: 5560,
};

// Module health status
export enum HealthStatus {
  OK = "OK",
  WARN = "WARN",
  EXPIRED = "EXPIRED",
  UNKNOWN = "UNKNOWN",
}

// Module info from engine
export interface ModuleInfo {
  moduleId: string;
  interfaces: string[];
  health: HealthStatus;
  liveness: number;
  lastSeen: number;
}

// Event log entry
export interface EventEntry {
  timestamp: number;
  event: string;
  sender: string;
  recipient?: string;
  type: string; // on, ack, whisper, on_common, broadcast
}

// Engine status from admin endpoint
export interface EngineStatus {
  status: string;
  uptime: number;
  moduleCount: number;
  eventCount: number;
  registerCount: number;
}

// Connection state
export enum ConnectionState {
  DISCONNECTED = "DISCONNECTED",
  CONNECTING = "CONNECTING",
  CONNECTED = "CONNECTED",
  RECONNECTING = "RECONNECTING",
}

// Application state
export interface AppState {
  connection: ConnectionState;
  engineStatus: EngineStatus | null;
  modules: Map<string, ModuleInfo>;
  events: EventEntry[];
  stats: {
    eventsPerSecond: number;
    totalEvents: number;
    heartbeatOk: number;
    heartbeatWarn: number;
    heartbeatExpired: number;
  };
  paused: boolean;
}
