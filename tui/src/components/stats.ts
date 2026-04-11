import { BoxRenderable, TextRenderable } from "@opentui/core";
import type { CliRenderer } from "@opentui/core";
import { AppState } from "../types.js";

export function createStatsBar(renderer: CliRenderer): BoxRenderable {
  const statsBox = new BoxRenderable(renderer, {
    height: 3,
    border: true,
    flexDirection: "row",
    justifyContent: "space-between",
    paddingLeft: 1,
    paddingRight: 1,
  });

  const leftText = new TextRenderable(renderer, {
    content: "Events/s: 0  Total: 0",
    fg: "#FFFFFF",
  });

  const rightText = new TextRenderable(renderer, {
    content: "HB OK: 0  WARN: 0  EXPIRED: 0",
    fg: "#FFFFFF",
  });

  statsBox.add(leftText);
  statsBox.add(rightText);

  return statsBox;
}

export function updateStatsBar(
  leftText: TextRenderable,
  rightText: TextRenderable,
  stats: AppState["stats"]
): void {
  // Update left text: Events/s and Total
  leftText.content = `Events/s: ${stats.eventsPerSecond}  Total: ${stats.totalEvents}`;

  // Build right text with colored counts
  // Note: Since we can only set one fg color per Text, we use the most critical color
  // or default to white. For more granular coloring, we'd need multiple Text elements.
  let criticalityColor = "#00FF00"; // Default green (all OK)
  if (stats.heartbeatExpired > 0) {
    criticalityColor = "#FF0000"; // Red if any expired
  } else if (stats.heartbeatWarn > 0) {
    criticalityColor = "#FFFF00"; // Yellow if any warn
  }

  rightText.content = `HB OK: ${stats.heartbeatOk}  WARN: ${stats.heartbeatWarn}  EXPIRED: ${stats.heartbeatExpired}`;
  rightText.fg = criticalityColor;
}
