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
  timestamp: number; // microseconds since epoch
  event: string;
  sender: string;
  recipient?: string;
  type: string; // on, ack, whisper, on_common, broadcast
  payload: Record<string, unknown>;
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
  processes: ProcessInfo[];
  selectedProcess: number;  // -1 = none
  selectedModuleId: string | null; // null = no filter
}

// Process management types
export enum ProcessState {
  STOPPED = "STOPPED",
  STARTING = "STARTING",
  RUNNING = "RUNNING",
  STOPPING = "STOPPING",
  CRASHED = "CRASHED",
}

export interface ProcessConfig {
  name: string;
  command: string;
  args: string[];
  cwd?: string;          // Override workdir for this process
  env?: Record<string, string>;
  autoStart?: boolean;
  dependsOn?: string[];
}

export interface ProcessesConfig {
  workdir?: string;       // Working directory for all processes (relative to config file)
  processes: ProcessConfig[];
}

export interface ProcessInfo {
  name: string;
  state: ProcessState;
  pid?: number;
  exitCode?: number | null;
  startedAt?: number;     // timestamp ms
  stoppedAt?: number;     // timestamp ms
}
