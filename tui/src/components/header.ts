import { BoxRenderable, TextRenderable } from "@opentui/core";
import type { CliRenderer } from "@opentui/core";
import { ConnectionState } from "../types.js";

export function createHeader(renderer: CliRenderer): BoxRenderable {
  const headerBox = new BoxRenderable(renderer, {
    height: 3,
    border: true,
    flexDirection: "row",
    justifyContent: "space-between",
    paddingLeft: 1,
    paddingRight: 1,
  });

  const titleText = new TextRenderable(renderer, {
    content: "TYCHE ENGINE DASHBOARD",
    fg: "#00BFFF",
  });

  const statusText = new TextRenderable(renderer, {
    content: "Status: DISCONNECTED  Up: 0s",
    fg: "#FF0000",
  });

  headerBox.add(titleText);
  headerBox.add(statusText);

  return headerBox;
}

export function updateHeader(
  statusText: TextRenderable,
  state: { connectionState: ConnectionState; uptime: number }
): void {
  // Format uptime as human readable
  const formatUptime = (seconds: number): string => {
    if (seconds < 60) {
      return `${seconds}s`;
    } else if (seconds < 3600) {
      const mins = Math.floor(seconds / 60);
      const secs = seconds % 60;
      return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
    } else {
      const hours = Math.floor(seconds / 3600);
      const mins = Math.floor((seconds % 3600) / 60);
      return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
    }
  };

  // Determine color based on connection state
  const colorMap: Record<ConnectionState, string> = {
    [ConnectionState.CONNECTED]: "#00FF00",
    [ConnectionState.DISCONNECTED]: "#FF0000",
    [ConnectionState.RECONNECTING]: "#FFFF00",
    [ConnectionState.CONNECTING]: "#FFFF00",
  };

  const fg = colorMap[state.connectionState] || "#808080";
  const formattedUptime = formatUptime(state.uptime);

  statusText.content = `Status: ${state.connectionState}  Up: ${formattedUptime}`;
  statusText.fg = fg;
}
