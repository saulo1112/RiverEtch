import { useState } from "react";

/** The case view's panels that fold to a summary. */
export type FoldingPanel = "file" | "record";

// Where the panels' open state is kept, across cases and visits. Storage can be missing, full or
// blocked (private windows, previews): the panels then just start collapsed every time.
const STORAGE_KEY = "riveretch:case-panels";

// What was stored (anything: only a `true` opens a panel).
function readStored(): Readonly<Record<string, unknown>> {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "{}");
    return typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)
      ? { ...parsed }
      : {};
  } catch {
    return {};
  }
}

function writeStored(panel: FoldingPanel, open: boolean): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...readStored(), [panel]: open }));
  } catch {
    // Not kept: the panel still opens and closes.
  }
}

/**
 * Whether a panel shows its details: collapsed by default, remembered once toggled.
 *
 * @param panel - The panel.
 * @returns Its open state and a setter that also stores it.
 */
export function usePanelOpen(panel: FoldingPanel): readonly [boolean, (open: boolean) => void] {
  const [open, setOpen] = useState(() => readStored()[panel] === true);
  const set = (next: boolean) => {
    setOpen(next);
    writeStored(panel, next);
  };
  return [open, set];
}
