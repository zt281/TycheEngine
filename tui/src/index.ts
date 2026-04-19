import { createCliRenderer } from "@opentui/core";
import { ConnectionManager } from "./connection.js";
import { ProcessManager } from "./process-manager.js";
import { AppStateManager } from "./state.js";
import { createLayout, updateLayout } from "./layout.js";
import { ConnectionConfig, DEFAULT_CONFIG } from "./types.js";

interface ParsedArgs {
  connectionConfig: ConnectionConfig;
  configPath: string;
}

function parseArgs(): ParsedArgs {
  const args = process.argv.slice(2);
  const connectionConfig: ConnectionConfig = { ...DEFAULT_CONFIG };
  let configPath = "tyche-processes.json";

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    switch (arg) {
      case "--host":
        if (i + 1 < args.length) {
          connectionConfig.host = args[++i];
        }
        break;
      case "--event-port":
        if (i + 1 < args.length) {
          connectionConfig.eventPort = parseInt(args[++i], 10);
        }
        break;
      case "--heartbeat-port":
        if (i + 1 < args.length) {
          connectionConfig.heartbeatPort = parseInt(args[++i], 10);
        }
        break;
      case "--admin-port":
        if (i + 1 < args.length) {
          connectionConfig.adminPort = parseInt(args[++i], 10);
        }
        break;
      case "--config":
        if (i + 1 < args.length) {
          configPath = args[++i];
        }
        break;
    }
  }

  return { connectionConfig, configPath };
}

async function main(): Promise<void> {
  // 1. Parse CLI args
  const { connectionConfig, configPath } = parseArgs();

  // 2. Create ProcessManager and load config
  const processManager = new ProcessManager();
  try {
    await processManager.loadConfig(configPath);
  } catch (error) {
    // Config file not found is non-fatal - just no processes to manage
  }

  // 3. Create ConnectionManager with config
  const connectionManager = new ConnectionManager(connectionConfig);

  // 4. Create AppStateManager with connection manager and process manager
  const stateManager = new AppStateManager(connectionManager, processManager);

  // 4. Initialize OpenTUI renderer
  const renderer = await createCliRenderer({
    screenMode: "alternate-screen",
    exitOnCtrlC: false, // We handle Ctrl+C ourselves
    targetFps: 10, // Low FPS since this is a monitoring dashboard
    maxFps: 30,
  });

  // 5. Create layout and get refs
  const refs = createLayout(renderer);
  renderer.root.add(refs.root);

  // 6. Start live rendering
  renderer.requestLive();

  // 7. Set up keyboard handlers
  renderer.keyInput.on("keypress", (event) => {
    switch (event.name) {
      case "tab":
        stateManager.selectNext();
        break;
      case "q":
      case "Q":
        shutdown();
        break;
      case "p":
      case "P":
        stateManager.togglePause();
        break;
      case "c":
      case "C":
        stateManager.clearEvents();
        break;
      case "s":
      case "S":
        stateManager.startSelectedProcess();
        break;
      case "x":
      case "X":
        stateManager.stopSelectedProcess();
        break;
      case "r":
      case "R":
        stateManager.restartSelectedProcess();
        break;
      case "a":
      case "A":
        stateManager.startAllProcesses();
        break;
      case "k":
      case "K":
        stateManager.killSelectedProcess();
        break;
    }
    // Ctrl+C also triggers shutdown
    if (event.ctrl && event.name === "c") {
      shutdown();
    }
  });

  // 8. Set up periodic UI refresh (every 500ms)
  const uiRefreshTimer = setInterval(() => {
    const state = stateManager.getState();
    updateLayout(refs, state);
  }, 500);

  // 9. Shutdown handler
  let isShuttingDown = false;
  async function shutdown() {
    if (isShuttingDown) return;
    isShuttingDown = true;

    clearInterval(uiRefreshTimer);
    await stateManager.stop();
    renderer.dropLive();
    renderer.destroy();
    // Allow ZeroMQ to flush pending socket closures before hard exit
    await new Promise((r) => setTimeout(r, 500));
    process.exit(0);
  }

  // 10. Handle process signals
  process.on("SIGINT", shutdown);
  // SIGTERM works on Unix; on Windows, use 'exit' event as fallback
  if (process.platform !== "win32") {
    process.on("SIGTERM", shutdown);
  }

  // 11. Start the state manager (connects to engine, starts polling)
  try {
    await stateManager.start();
  } catch (error) {
    // If connection fails, log but don't crash - UI will show disconnected state
    console.error("Failed to connect to engine:", error);
  }
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
