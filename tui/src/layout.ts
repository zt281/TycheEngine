import { BoxRenderable } from "@opentui/core";
import type { CliRenderer, BoxRenderable as BoxRenderableType, TextRenderable } from "@opentui/core";
import { AppState } from "./types.js";
import { createHeader, updateHeader } from "./components/header.js";
import { createModulePanel, updateModulePanel } from "./components/modules.js";
import { createEventLog, updateEventLog } from "./components/event-log.js";
import { createStatsBar, updateStatsBar } from "./components/stats.js";
import { createFooter } from "./components/footer.js";

export interface LayoutRefs {
  root: BoxRenderableType;
  renderer: CliRenderer;
  headerStatusText: TextRenderable;
  moduleTitleText: TextRenderable;
  moduleContentBox: BoxRenderableType;
  eventLogContent: BoxRenderableType;
  statsLeftText: TextRenderable;
  statsRightText: TextRenderable;
}

export function createLayout(renderer: CliRenderer): LayoutRefs {
  // Create root container
  const root = new BoxRenderable(renderer, {
    width: "100%",
    height: "100%",
    flexDirection: "column",
  });

  // 1. Header
  const headerBox = createHeader(renderer);
  // Extract the status text (second child of header)
  const headerStatusText = headerBox.getChildren()[1] as TextRenderable;

  // 2. Middle row: Module panel + Event log
  const middleRow = new BoxRenderable(renderer, {
    flexDirection: "row",
    flexGrow: 1,
  });

  // Module panel
  const modulePanel = createModulePanel(renderer);
  const moduleTitleText = modulePanel.getChildren()[0] as TextRenderable;
  const moduleContentBox = modulePanel.getChildren()[1] as BoxRenderable;

  // Event log
  const eventLogPanel = createEventLog(renderer);
  const eventLogContent = eventLogPanel.getChildren()[1] as BoxRenderable;

  middleRow.add(modulePanel);
  middleRow.add(eventLogPanel);

  // 3. Stats bar
  const statsBar = createStatsBar(renderer);
  const statsLeftText = statsBar.getChildren()[0] as TextRenderable;
  const statsRightText = statsBar.getChildren()[1] as TextRenderable;

  // 4. Footer
  const footer = createFooter(renderer);

  // Assemble all components
  root.add(headerBox);
  root.add(middleRow);
  root.add(statsBar);
  root.add(footer);

  return {
    root,
    renderer,
    headerStatusText,
    moduleTitleText,
    moduleContentBox,
    eventLogContent,
    statsLeftText,
    statsRightText,
  };
}

export function updateLayout(refs: LayoutRefs, state: AppState): void {
  // Update header with connection state and uptime
  const uptime = state.engineStatus?.uptime ?? 0;
  updateHeader(refs.headerStatusText, {
    connectionState: state.connection,
    uptime,
  });

  // Update module panel
  const modulesArray = Array.from(state.modules.values()).sort((a, b) =>
    a.moduleId.localeCompare(b.moduleId)
  );
  updateModulePanel(
    refs.renderer,
    refs.moduleTitleText,
    refs.moduleContentBox,
    modulesArray
  );

  // Update event log
  updateEventLog(refs.renderer, refs.eventLogContent, state.events);

  // Update stats bar
  updateStatsBar(refs.statsLeftText, refs.statsRightText, state.stats);
}
