import { BoxRenderable, TextRenderable } from "@opentui/core";
import type { CliRenderer } from "@opentui/core";

export function createFooter(renderer: CliRenderer): BoxRenderable {
  const footerBox = new BoxRenderable(renderer, {
    height: 1,
    flexDirection: "row",
    justifyContent: "center",
  });

  const helpText = new TextRenderable(renderer, {
    content: "[q] Quit  [p] Pause  [c] Clear  [Tab] Next  [s] Start  [x] Stop  [r] Restart  [a] All  [k] Kill Sel",
    fg: "#808080",
  });

  footerBox.add(helpText);

  return footerBox;
}
