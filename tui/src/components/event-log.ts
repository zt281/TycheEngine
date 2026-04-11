import { BoxRenderable, TextRenderable } from "@opentui/core";
import type { CliRenderer } from "@opentui/core";
import { EventEntry } from "../types.js";

export function createEventLog(renderer: CliRenderer): BoxRenderable {
  const panelBox = new BoxRenderable(renderer, {
    flexGrow: 1,
    border: true,
    flexDirection: "column",
  });

  const titleText = new TextRenderable(renderer, {
    content: "Event Log",
    fg: "#00BFFF",
  });

  // Use a regular Box for event entries (ScrollBox if available would be better)
  const contentBox = new BoxRenderable(renderer, {
    flexDirection: "column",
    flexGrow: 1,
  });

  panelBox.add(titleText);
  panelBox.add(contentBox);

  return panelBox;
}

export function updateEventLog(
  renderer: CliRenderer,
  contentBox: BoxRenderable,
  events: EventEntry[]
): void {
  // Clear content
  const children = contentBox.getChildren();
  for (const child of children) {
    contentBox.remove(child.id);
  }

  // Color mapping by event type prefix
  const getEventColor = (type: string): string => {
    switch (type) {
      case "on":
        return "#6495ED"; // cornflower blue
      case "ack":
        return "#00FF00"; // green
      case "whisper":
        return "#FFD700"; // gold
      case "on_common":
        return "#00CED1"; // dark turquoise
      case "broadcast":
        return "#FF69B4"; // hot pink
      default:
        return "#FFFFFF"; // white
    }
  };

  // Format timestamp as HH:MM:SS
  const formatTime = (timestamp: number): string => {
    const date = new Date(timestamp);
    return date.toTimeString().slice(0, 8);
  };

  // Show last 30 events (most recent last)
  const recentEvents = events.slice(-30);

  for (const entry of recentEvents) {
    const timeStr = formatTime(entry.timestamp);
    const eventName = entry.event.padEnd(16, " ");
    const senderTruncated = entry.sender.slice(0, 8);

    const rowText = new TextRenderable(renderer, {
      content: `${timeStr} ${eventName} ${senderTruncated}`,
      fg: getEventColor(entry.type),
    });
    contentBox.add(rowText);
  }

  // Show placeholder if no events
  if (events.length === 0) {
    const emptyText = new TextRenderable(renderer, {
      content: "  No events received",
      fg: "#808080",
    });
    contentBox.add(emptyText);
  }
}
