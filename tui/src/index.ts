import { createCliRenderer } from "@opentui/core";
import { ConnectionManager } from "./connection.js";
import { AppStateManager } from "./state.js";
import { createLayout, updateLayout } from "./layout.js";
import { ConnectionConfig, DEFAULT_CONFIG } from "./types.js";

function parseArgs(): ConnectionConfig {
  const args = process.argv.slice(2);
  const config: ConnectionConfig = { ...DEFAULT_CONFIG };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    switch (arg) {
      case "--host":
        if (i + 1 < args.length) {
          config.host = args[++i];
        }
        break;
      case "--event-port":
        if (i + 1 < args.length) {
          config.eventPort = parseInt(args[++i], 10);
        }
        break;
      case "--heartbeat-port":
        if (i + 1 < args.length) {
          config.heartbeatPort = parseInt(args[++i], 10);
        }
        break;
      case "--admin-port":
        if (i + 1 < args.length) {
          config.adminPort = parseInt(args[++i], 10);
        }
        break;
    }
  }

  return config;
}

async function main(): Promise<void> {
  // 1. Parse CLI args into ConnectionConfig
  const config = parseArgs();

  // 2. Create ConnectionManager with config
  const connectionManager = new ConnectionManager(config);

  // 3. Create AppStateManager with connection manager
  const stateManager = new AppStateManager(connectionManager);

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

  // 10. Shutdown handler
  let isShuttingDown = false;
  async function shutdown() {
    if (isShuttingDown) return;
    isShuttingDown = true;

    clearInterval(uiRefreshTimer);
    await stateManager.stop();
    renderer.dropLive();
    renderer.destroy();
    process.exit(0);
  }

  // 11. Handle process signals
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);

  // 9. Start the state manager (connects to engine, starts polling)
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
