import {
  AppState,
  ConnectionState,
  EngineStatus,
  EventEntry,
  ModuleInfo,
  HealthStatus,
} from "./types.js";
import { ConnectionManager } from "./connection.js";

const MAX_EVENTS = 500;
const RATE_WINDOW_MS = 5000; // 5 seconds for rate calculation
const ADMIN_POLL_INTERVAL_MS = 3000; // 3 seconds
const STATS_INTERVAL_MS = 1000; // 1 second

export class AppStateManager {
  // State properties
  private connection: ConnectionState = ConnectionState.DISCONNECTED;
  private engineStatus: EngineStatus | null = null;
  private modules: Map<string, ModuleInfo> = new Map();
  private events: EventEntry[] = [];
  private stats = {
    eventsPerSecond: 0,
    totalEvents: 0,
    heartbeatOk: 0,
    heartbeatWarn: 0,
    heartbeatExpired: 0,
  };
  private paused: boolean = false;

  // Private state for rate calculation
  private eventCountWindow: number[] = []; // timestamps of recent events
  private adminPollTimer: ReturnType<typeof setInterval> | null = null;
  private statsTimer: ReturnType<typeof setInterval> | null = null;

  private connectionManager: ConnectionManager;

  constructor(connectionManager: ConnectionManager) {
    this.connectionManager = connectionManager;
  }

  async start(): Promise<void> {
    // Wire up ConnectionManager callbacks
    this.connectionManager.setOnEvent((entry: EventEntry) => {
      this.handleEvent(entry);
    });
    this.connectionManager.setOnHeartbeat((moduleId: string) => {
      this.handleHeartbeat(moduleId);
    });
    this.connectionManager.setOnStateChange((state: ConnectionState) => {
      this.connection = state;
    });

    // Connect the ConnectionManager
    await this.connectionManager.connect();

    // Start periodic admin polling
    this.adminPollTimer = setInterval(() => {
      this.pollAdmin().catch((error) => {
        // Silently skip failed polling cycles
      });
    }, ADMIN_POLL_INTERVAL_MS);

    // Start periodic stats recalculation
    this.statsTimer = setInterval(() => {
      this.recalcStats();
    }, STATS_INTERVAL_MS);
  }

  async stop(): Promise<void> {
    // Clear intervals
    if (this.adminPollTimer) {
      clearInterval(this.adminPollTimer);
      this.adminPollTimer = null;
    }
    if (this.statsTimer) {
      clearInterval(this.statsTimer);
      this.statsTimer = null;
    }

    // Disconnect ConnectionManager
    await this.connectionManager.disconnect();
  }

  handleEvent(entry: EventEntry): void {
    // If paused, skip (don't add to events)
    if (this.paused) {
      return;
    }

    // Add entry to events array
    this.events.push(entry);

    // If events.length > MAX_EVENTS, shift oldest entries off
    if (this.events.length > MAX_EVENTS) {
      this.events.shift();
    }

    // Record timestamp in eventCountWindow for rate calculation
    this.eventCountWindow.push(Date.now());

    // Increment stats.totalEvents
    this.stats.totalEvents++;
  }

  handleHeartbeat(moduleId: string): void {
    // If module exists in modules map, update its lastSeen to Date.now()
    const module = this.modules.get(moduleId);
    if (module) {
      module.lastSeen = Date.now();
    }
  }

  async pollAdmin(): Promise<void> {
    // Query status via ConnectionManager.queryStatus()
    const status = await this.connectionManager.queryStatus();
    if (status) {
      this.engineStatus = status;
    }

    // Query modules via ConnectionManager.queryModules()
    const modulesArray = await this.connectionManager.queryModules();
    if (modulesArray) {
      // Rebuild the modules map from the array
      this.modules.clear();
      for (const mod of modulesArray) {
        this.modules.set(mod.moduleId, mod);
      }
    }

    // Recalculate heartbeat summary stats
    this.recalcHeartbeatStats();
  }

  private recalcHeartbeatStats(): void {
    let ok = 0;
    let warn = 0;
    let expired = 0;

    for (const mod of this.modules.values()) {
      switch (mod.health) {
        case HealthStatus.OK:
          ok++;
          break;
        case HealthStatus.WARN:
          warn++;
          break;
        case HealthStatus.EXPIRED:
          expired++;
          break;
      }
    }

    this.stats.heartbeatOk = ok;
    this.stats.heartbeatWarn = warn;
    this.stats.heartbeatExpired = expired;
  }

  recalcStats(): void {
    const now = Date.now();

    // Filter eventCountWindow to only timestamps within last RATE_WINDOW_MS
    this.eventCountWindow = this.eventCountWindow.filter(
      (timestamp) => now - timestamp < RATE_WINDOW_MS
    );

    // Calculate eventsPerSecond = eventCountWindow.length / 5 (rounded to 1 decimal)
    this.stats.eventsPerSecond =
      Math.round((this.eventCountWindow.length / (RATE_WINDOW_MS / 1000)) * 10) /
      10;

    // Update heartbeat counts from current modules map
    this.recalcHeartbeatStats();
  }

  getState(): AppState {
    return {
      connection: this.connection,
      engineStatus: this.engineStatus,
      modules: new Map(this.modules),
      events: [...this.events],
      stats: { ...this.stats },
      paused: this.paused,
    };
  }

  clearEvents(): void {
    this.events = [];
    this.eventCountWindow = [];
  }

  togglePause(): void {
    this.paused = !this.paused;
  }

  getModules(): ModuleInfo[] {
    return Array.from(this.modules.values()).sort((a, b) =>
      a.moduleId.localeCompare(b.moduleId)
    );
  }

  getRecentEvents(count: number = 50): EventEntry[] {
    // Return the last N events (default 50), most recent last
    const startIndex = Math.max(0, this.events.length - count);
    return this.events.slice(startIndex);
  }
}
