import { BoxRenderable } from "@opentui/core";
import type { CliRenderer, BoxRenderable as BoxRenderableType, TextRenderable } from "@opentui/core";
import { AppState } from "./types.js";
import { createHeader, updateHeader } from "./components/header.js";
import { createModulePanel, updateModulePanel } from "./components/modules.js";
import { createProcessPanel, updateProcessPanel } from "./components/processes.js";
import { createEventLog, updateEventLog } from "./components/event-log.js";
import { createStatsBar, updateStatsBar } from "./components/stats.js";
import { createFooter } from "./components/footer.js";

export interface LayoutRefs {
  root: BoxRenderableType;
  renderer: CliRenderer;
  headerStatusText: TextRenderable;
  moduleTitleText: TextRenderable;
  moduleContentBox: BoxRenderableType;
  processTitleText: TextRenderable;
  processContentBox: BoxRenderableType;
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

  // Left column container for process panel + module panel
  const leftColumn = new BoxRenderable(renderer, {
    width: "35%",
    flexGrow: 0,
    flexDirection: "column",
  });

  // Process panel (top of left column)
  const processPanel = createProcessPanel(renderer);
  const processTitleText = processPanel.getChildren()[0] as TextRenderable;
  const processContentBox = processPanel.getChildren()[1] as BoxRenderable;

  // Module panel (bottom of left column, takes remaining space)
  const modulePanel = createModulePanel(renderer);
  const moduleTitleText = modulePanel.getChildren()[0] as TextRenderable;
  const moduleContentBox = modulePanel.getChildren()[1] as BoxRenderable;

  leftColumn.add(processPanel);
  leftColumn.add(modulePanel);

  // Event log
  const eventLogPanel = createEventLog(renderer);
  const eventLogContent = eventLogPanel.getChildren()[1] as BoxRenderable;

  middleRow.add(leftColumn);
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
    processTitleText,
    processContentBox,
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
    modulesArray,
    state.selectedModuleId
  );

  // Update process panel
  updateProcessPanel(
    refs.renderer,
    refs.processTitleText,
    refs.processContentBox,
    state.processes,
    state.selectedProcess
  );

  // Update event log
  updateEventLog(refs.renderer, refs.eventLogContent, state.events, state.selectedModuleId);

  // Update stats bar
  updateStatsBar(refs.statsLeftText, refs.statsRightText, state.stats);
}
