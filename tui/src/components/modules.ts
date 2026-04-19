import { BoxRenderable, TextRenderable } from "@opentui/core";
import type { CliRenderer } from "@opentui/core";
import { ModuleInfo, HealthStatus } from "../types.js";

export function createModulePanel(renderer: CliRenderer): BoxRenderable {
  const panelBox = new BoxRenderable(renderer, {
    width: "100%",
    flexGrow: 1,
    border: true,
    flexDirection: "column",
  });

  const titleText = new TextRenderable(renderer, {
    content: "Modules (0)",
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

export function updateModulePanel(
  renderer: CliRenderer,
  titleText: TextRenderable,
  contentBox: BoxRenderable,
  modules: ModuleInfo[],
  selectedModuleId: string | null
): void {
  // Update title
  titleText.content = `Modules (${modules.length})`;

  // Clear content box children
  const children = contentBox.getChildren();
  for (const child of children) {
    contentBox.remove(child.id);
  }

  // Health color mapping
  const healthColors: Record<HealthStatus, string> = {
    [HealthStatus.OK]: "#00FF00",
    [HealthStatus.WARN]: "#FFFF00",
    [HealthStatus.EXPIRED]: "#FF0000",
    [HealthStatus.UNKNOWN]: "#808080",
  };

  // Build rows for each module
  for (const module of modules) {
    const isSelected = module.moduleId === selectedModuleId;
    const truncatedId = module.moduleId.slice(0, 12).padEnd(12, " ");
    const healthStr = module.health.padEnd(6, " ");
    const prefix = isSelected ? "> " : "  ";
    const rowText = new TextRenderable(renderer, {
      content: `${prefix}${truncatedId}  ${healthStr}`,
      fg: isSelected ? "#FFFFFF" : (healthColors[module.health] || "#808080"),
    });
    contentBox.add(rowText);
  }

  // Show placeholder if no modules
  if (modules.length === 0) {
    const emptyText = new TextRenderable(renderer, {
      content: "  No modules registered",
      fg: "#808080",
    });
    contentBox.add(emptyText);
  }
}
