import { ProcessConfig, ProcessesConfig, ProcessInfo, ProcessState } from "./types.js";
import { Subprocess } from "bun";
import { resolve, dirname } from "path";

interface ManagedProcess {
  config: ProcessConfig;
  state: ProcessState;
  proc: Subprocess | null;
  pid?: number;
  exitCode?: number | null;
  startedAt?: number;
  stoppedAt?: number;
}

export class ProcessManager {
  private processes: Map<string, ManagedProcess> = new Map();
  private workdir: string;
  private readonly isWindows = process.platform === "win32";

  constructor() {
    this.workdir = process.cwd();
  }

  // Load config from JSON file
  async loadConfig(configPath: string): Promise<void> {
    const fullPath = resolve(configPath);
    const file = Bun.file(fullPath);
    const config: ProcessesConfig = await file.json();

    // Resolve workdir relative to config file location
    if (config.workdir) {
      this.workdir = resolve(dirname(fullPath), config.workdir);
    }

    // Initialize managed processes from config
    for (const procConfig of config.processes) {
      this.processes.set(procConfig.name, {
        config: procConfig,
        state: ProcessState.STOPPED,
        proc: null,
      });
    }
  }

  // Start a single process by name
  async startProcess(name: string): Promise<boolean> {
    const managed = this.processes.get(name);
    if (!managed) return false;
    if (managed.state === ProcessState.RUNNING || managed.state === ProcessState.STARTING) {
      return false; // Already running
    }

    // Check dependsOn - all dependencies must be RUNNING
    if (managed.config.dependsOn) {
      for (const dep of managed.config.dependsOn) {
        const depProcess = this.processes.get(dep);
        if (!depProcess || depProcess.state !== ProcessState.RUNNING) {
          return false; // Dependency not running
        }
      }
    }

    managed.state = ProcessState.STARTING;
    managed.exitCode = null;
    managed.stoppedAt = undefined;

    try {
      const cwd = managed.config.cwd
        ? resolve(this.workdir, managed.config.cwd)
        : this.workdir;

      const env = { ...process.env, ...(managed.config.env || {}) };

      const proc = Bun.spawn([managed.config.command, ...managed.config.args], {
        cwd,
        env,
        stdout: "ignore",
        stderr: "ignore",
        onExit: (_proc, exitCode, _signalCode, _error) => {
          // Only update if this is still the current process
          if (managed.proc === _proc) {
            if (managed.state === ProcessState.STOPPING) {
              managed.state = ProcessState.STOPPED;
            } else {
              managed.state = ProcessState.CRASHED;
            }
            managed.exitCode = exitCode;
            managed.stoppedAt = Date.now();
            managed.proc = null;
            managed.pid = undefined;
          }
        },
      });

      managed.proc = proc;
      managed.pid = proc.pid;
      managed.startedAt = Date.now();
      managed.state = ProcessState.RUNNING;
      return true;
    } catch (error) {
      managed.state = ProcessState.CRASHED;
      managed.stoppedAt = Date.now();
      return false;
    }
  }

  // Stop a single process by name
  async stopProcess(name: string): Promise<boolean> {
    const managed = this.processes.get(name);
    if (!managed || !managed.proc) return false;
    if (managed.state !== ProcessState.RUNNING && managed.state !== ProcessState.STARTING) {
      return false;
    }

    managed.state = ProcessState.STOPPING;

    try {
      if (this.isWindows) {
        // On Windows, use taskkill for process tree termination
        if (managed.pid) {
          const result = Bun.spawnSync(
            ["taskkill", "/T", "/F", "/PID", String(managed.pid)],
            { stdout: "ignore", stderr: "ignore" }
          );
          if (result.exitCode !== 0) {
            // taskkill failed — fallback to direct kill
            managed.proc.kill();
            // Give proc.kill() a moment, then force-kill if still stopping
            setTimeout(() => {
              if (managed.proc && managed.state === ProcessState.STOPPING) {
                try {
                  managed.proc!.kill(9);
                } catch {
                  /* ignore */
                }
              }
            }, 3000);
          }
        } else {
          managed.proc.kill();
        }
      } else {
        // Unix: SIGTERM for graceful shutdown
        managed.proc.kill();
        // Wait up to 5 seconds, then SIGKILL
        const timeout = setTimeout(() => {
          if (managed.proc && managed.state === ProcessState.STOPPING) {
            managed.proc.kill(9);
          }
        }, 5000);

        const checkInterval = setInterval(() => {
          if (managed.state !== ProcessState.STOPPING) {
            clearTimeout(timeout);
            clearInterval(checkInterval);
          }
        }, 100);
      }

      return true;
    } catch (error) {
      managed.state = ProcessState.STOPPED;
      managed.proc = null;
      managed.pid = undefined;
      managed.stoppedAt = Date.now();
      return false;
    }
  }

  // Restart a process
  async restartProcess(name: string): Promise<boolean> {
    const managed = this.processes.get(name);
    if (!managed) return false;

    if (managed.state === ProcessState.RUNNING || managed.state === ProcessState.STARTING) {
      await this.stopProcess(name);
      // Wait for process to stop (up to 6 seconds)
      let waited = 0;
      while ((managed.state as ProcessState) === ProcessState.STOPPING && waited < 6000) {
        await new Promise(r => setTimeout(r, 100));
        waited += 100;
      }
    }

    return this.startProcess(name);
  }

  // Start all processes respecting dependsOn order
  async startAll(): Promise<void> {
    // Topological sort based on dependsOn
    const sorted = this.topologicalSort();
    for (const name of sorted) {
      const managed = this.processes.get(name);
      if (managed && managed.config.autoStart !== false) {
        await this.startProcess(name);
        // Small delay between starts for stability
        await new Promise(r => setTimeout(r, 500));
      }
    }
  }

  // Force-kill a single process by name
  async killProcess(name: string): Promise<boolean> {
    const managed = this.processes.get(name);
    if (!managed || !managed.proc) return false;
    if (managed.state !== ProcessState.RUNNING && managed.state !== ProcessState.STARTING) {
      return false;
    }

    managed.state = ProcessState.STOPPING;

    try {
      if (this.isWindows && managed.pid) {
        Bun.spawnSync(
          ["taskkill", "/T", "/F", "/PID", String(managed.pid)],
          { stdout: "ignore", stderr: "ignore" }
        );
      } else {
        managed.proc.kill(9);
      }
      return true;
    } catch {
      managed.state = ProcessState.STOPPED;
      managed.proc = null;
      managed.pid = undefined;
      managed.stoppedAt = Date.now();
      return false;
    }
  }

  // Stop all running processes (reverse dependency order)
  async stopAll(): Promise<void> {
    const sorted = this.topologicalSort().reverse();
    for (const name of sorted) {
      const managed = this.processes.get(name);
      if (managed && (managed.state === ProcessState.RUNNING || managed.state === ProcessState.STARTING)) {
        await this.stopProcess(name);
      }
    }
    // Wait for processes to fully terminate
    await new Promise(r => setTimeout(r, this.isWindows ? 500 : 1000));
  }

  // Get current state of all processes
  getProcesses(): ProcessInfo[] {
    const result: ProcessInfo[] = [];
    for (const [name, managed] of this.processes) {
      result.push({
        name,
        state: managed.state,
        pid: managed.pid,
        exitCode: managed.exitCode,
        startedAt: managed.startedAt,
        stoppedAt: managed.stoppedAt,
      });
    }
    return result;
  }

  // Get process count
  getProcessCount(): number {
    return this.processes.size;
  }

  // Get process by index (for keyboard selection)
  getProcessNameByIndex(index: number): string | undefined {
    const names = Array.from(this.processes.keys());
    return names[index];
  }

  // Topological sort of process names based on dependsOn
  private topologicalSort(): string[] {
    const visited = new Set<string>();
    const sorted: string[] = [];

    const visit = (name: string) => {
      if (visited.has(name)) return;
      visited.add(name);

      const managed = this.processes.get(name);
      if (managed?.config.dependsOn) {
        for (const dep of managed.config.dependsOn) {
          visit(dep);
        }
      }
      sorted.push(name);
    };

    for (const name of this.processes.keys()) {
      visit(name);
    }

    return sorted;
  }
}
