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
  events: EventEntry[],
  selectedModuleId: string | null
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

  // Format timestamp as HH:MM:SS.mmmuuu (microseconds)
  const formatTime = (timestampMicros: number): string => {
    const ms = Math.floor(timestampMicros / 1000);
    const micros = timestampMicros % 1000;
    const date = new Date(ms);
    const hh = String(date.getHours()).padStart(2, "0");
    const mm = String(date.getMinutes()).padStart(2, "0");
    const ss = String(date.getSeconds()).padStart(2, "0");
    const mmm = String(date.getMilliseconds()).padStart(3, "0");
    const uuu = String(micros).padStart(3, "0");
    return `${hh}:${mm}:${ss}.${mmm}${uuu}`;
  };

  // Format payload preview
  const formatPayload = (payload: Record<string, unknown>): string => {
    try {
      const str = JSON.stringify(payload);
      return str.length > 25 ? str.slice(0, 25) + "..." : str;
    } catch {
      return "{...}";
    }
  };

  // Filter events by selected module, then show last 30
  const eventsToShow = selectedModuleId
    ? events.filter((e) => e.sender === selectedModuleId)
    : events;
  const recentEvents = eventsToShow.slice(-30);

  for (const entry of recentEvents) {
    const timeStr = formatTime(entry.timestamp);
    const eventName = entry.event.slice(0, 14).padEnd(14, " ");
    const senderTruncated = entry.sender.slice(0, 8);
    const payloadStr = formatPayload(entry.payload);
    const payloadPart = payloadStr ? `  ${payloadStr}` : "";

    const rowText = new TextRenderable(renderer, {
      content: `${timeStr} ${eventName} ${senderTruncated}${payloadPart}`,
      fg: getEventColor(entry.type),
    });
    contentBox.add(rowText);
  }

  // Show placeholder if no events (or no matching filtered events)
  if (recentEvents.length === 0) {
    const msg = selectedModuleId
      ? `  No events from ${selectedModuleId.slice(0, 16)}`
      : "  No events received";
    const emptyText = new TextRenderable(renderer, {
      content: msg,
      fg: "#808080",
    });
    contentBox.add(emptyText);
  }
}
