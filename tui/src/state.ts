import {
  AppState,
  ConnectionState,
  EngineStatus,
  EventEntry,
  ModuleInfo,
  HealthStatus,
  ProcessInfo,
} from "./types.js";
import { ConnectionManager } from "./connection.js";
import { ProcessManager } from "./process-manager.js";

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
  private processes: ProcessInfo[] = [];
  private selectedIndex: number = -1;

  // Private state for rate calculation
  private eventCountWindow: number[] = []; // timestamps of recent events
  private adminPollTimer: ReturnType<typeof setInterval> | null = null;
  private statsTimer: ReturnType<typeof setInterval> | null = null;
  private processPollTimer: ReturnType<typeof setInterval> | null = null;

  private connectionManager: ConnectionManager;
  private processManager: ProcessManager | null;

  constructor(connectionManager: ConnectionManager, processManager: ProcessManager | null = null) {
    this.connectionManager = connectionManager;
    this.processManager = processManager;
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

    // Start process polling if processManager exists
    if (this.processManager) {
      // Start autoStart processes
      await this.processManager.startAll();
      // Poll process state every second
      this.processPollTimer = setInterval(() => {
        if (this.processManager) {
          this.updateProcesses(this.processManager.getProcesses());
        }
      }, 1000);
    }
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
    if (this.processPollTimer) {
      clearInterval(this.processPollTimer);
      this.processPollTimer = null;
    }

    // Stop all managed processes
    if (this.processManager) {
      await this.processManager.stopAll();
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
      processes: [...this.processes],
      selectedProcess: this.getSelectedProcessIndex(),
      selectedModuleId: this.getSelectedModuleId(),
    };
  }

  selectNext(): void {
    const processCount = this.processManager?.getProcessCount() ?? 0;
    const moduleCount = this.modules.size;
    const totalItems = processCount + moduleCount;
    if (totalItems === 0) {
      this.selectedIndex = -1;
      return;
    }
    this.selectedIndex = (this.selectedIndex + 1) % totalItems;
  }

  getSelectedProcessIndex(): number {
    const processCount = this.processManager?.getProcessCount() ?? 0;
    if (this.selectedIndex >= 0 && this.selectedIndex < processCount) {
      return this.selectedIndex;
    }
    return -1;
  }

  getSelectedModuleId(): string | null {
    const processCount = this.processManager?.getProcessCount() ?? 0;
    const moduleIndex = this.selectedIndex - processCount;
    const modules = this.getModules();
    if (moduleIndex >= 0 && moduleIndex < modules.length) {
      return modules[moduleIndex].moduleId;
    }
    return null;
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

  updateProcesses(processes: ProcessInfo[]): void {
    this.processes = processes;
  }

  setSelectedProcess(index: number): void {
    this.selectedIndex = index;
  }

  // Process management delegation methods
  selectProcess(index: number): void {
    this.setSelectedProcess(index);
  }

  async startSelectedProcess(): Promise<void> {
    const idx = this.getSelectedProcessIndex();
    if (!this.processManager || idx < 0) return;
    const name = this.processManager.getProcessNameByIndex(idx);
    if (name) {
      await this.processManager.startProcess(name);
    }
  }

  async stopSelectedProcess(): Promise<void> {
    const idx = this.getSelectedProcessIndex();
    if (!this.processManager || idx < 0) return;
    const name = this.processManager.getProcessNameByIndex(idx);
    if (name) {
      await this.processManager.stopProcess(name);
    }
  }

  async restartSelectedProcess(): Promise<void> {
    const idx = this.getSelectedProcessIndex();
    if (!this.processManager || idx < 0) return;
    const name = this.processManager.getProcessNameByIndex(idx);
    if (name) {
      await this.processManager.restartProcess(name);
    }
  }

  async startAllProcesses(): Promise<void> {
    if (!this.processManager) return;
    await this.processManager.startAll();
  }

  async stopAllProcesses(): Promise<void> {
    if (!this.processManager) return;
    await this.processManager.stopAll();
  }

  async killSelectedProcess(): Promise<void> {
    const idx = this.getSelectedProcessIndex();
    if (!this.processManager || idx < 0) return;
    const name = this.processManager.getProcessNameByIndex(idx);
    if (name) {
      await this.processManager.killProcess(name);
    }
  }
}
