import { BoxRenderable, TextRenderable } from "@opentui/core";
import type { CliRenderer } from "@opentui/core";
import { ProcessInfo, ProcessState } from "../types.js";

const STATE_ABBREV: Record<ProcessState, string> = {
  [ProcessState.RUNNING]: "RUN",
  [ProcessState.STARTING]: "...",
  [ProcessState.STOPPING]: "...",
  [ProcessState.CRASHED]: "ERR",
  [ProcessState.STOPPED]: "STP",
};

const STATE_COLORS: Record<ProcessState, string> = {
  [ProcessState.RUNNING]: "#00FF00",
  [ProcessState.STARTING]: "#FFFF00",
  [ProcessState.STOPPING]: "#FFFF00",
  [ProcessState.CRASHED]: "#FF0000",
  [ProcessState.STOPPED]: "#808080",
};

export function createProcessPanel(renderer: CliRenderer): BoxRenderable {
  const panelBox = new BoxRenderable(renderer, {
    width: "100%",
    flexGrow: 0,
    border: true,
    flexDirection: "column",
  });

  const titleText = new TextRenderable(renderer, {
    content: "Processes (0)",
    fg: "#00BFFF",
  });

  const contentBox = new BoxRenderable(renderer, {
    flexDirection: "column",
    flexGrow: 1,
  });

  panelBox.add(titleText);
  panelBox.add(contentBox);

  return panelBox;
}

export function updateProcessPanel(
  renderer: CliRenderer,
  titleText: TextRenderable,
  contentBox: BoxRenderable,
  processes: ProcessInfo[],
  selectedIndex: number
): void {
  // Update title
  titleText.content = `Processes (${processes.length})`;

  // Clear content box children
  const children = contentBox.getChildren();
  for (const child of children) {
    contentBox.remove(child.id);
  }

  // Build rows for each process
  for (let i = 0; i < processes.length; i++) {
    const proc = processes[i];
    const isSelected = i === selectedIndex;
    const stateStr = STATE_ABBREV[proc.state] || "???";
    const name = proc.name.padEnd(14, " ");
    const state = stateStr.padEnd(4, " ");

    const prefix = isSelected ? "> " : "  ";
    const content = `${prefix}${i + 1}. ${name}  ${state}`;

    const rowText = new TextRenderable(renderer, {
      content,
      fg: isSelected ? "#FFFFFF" : (STATE_COLORS[proc.state] || "#808080"),
    });
    contentBox.add(rowText);
  }

  // Show placeholder if no processes
  if (processes.length === 0) {
    const emptyText = new TextRenderable(renderer, {
      content: "  No processes configured",
      fg: "#808080",
    });
    contentBox.add(emptyText);
  }
}
