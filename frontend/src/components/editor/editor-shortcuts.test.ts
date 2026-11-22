import { describe, expect, it } from "vitest";
import en from "../../../messages/en/editor.json";
import { SHORTCUTS } from "./editor-workspace";


function lookup(messages: Record<string, unknown>, key: string): unknown {
  return key.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], messages);
}

describe("studio shortcuts dialog", () => {
  it("says Delete removes the selected B-roll or edit", () => {
    expect(SHORTCUTS.find(([keys]) => keys[0] === "Delete")?.[1]).toBe("shortcuts.removeSelection");
    expect(lookup(en, "shortcuts.removeSelection")).toBe("Remove the selected B-roll or edit");
  });

  it("has every label in the English catalog", () => {
    for (const [, key] of SHORTCUTS) {
      expect(typeof lookup(en, key), key).toBe("string");
    }
  });
});
