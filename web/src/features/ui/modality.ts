// Which input the visitor last used, on the root element (`data-modality`: "pointer" or
// "keyboard"), so focus rings show for keyboard users only. The browsers' own `:focus-visible`
// also rings an element the app focuses itself (a closed dialog handing focus back, a view that
// lands) after any key press, and the ring then stays under a mouse user's clicks; with this, a
// pointer press hides the rings and the next key brings them back.

/**
 * Starts tracking the input modality on the document's root element.
 *
 * @param root - The element that carries `data-modality` (the document's root).
 * @returns A function that stops tracking.
 */
export function trackInputModality(root: HTMLElement = document.documentElement): () => void {
  const onPointer = () => {
    root.dataset.modality = "pointer";
  };
  const onKey = (event: KeyboardEvent) => {
    // A shortcut with a modifier is not navigation.
    if (!event.metaKey && !event.ctrlKey && !event.altKey) {
      root.dataset.modality = "keyboard";
    }
  };
  window.addEventListener("pointerdown", onPointer, { capture: true, passive: true });
  window.addEventListener("keydown", onKey, { capture: true });
  return () => {
    window.removeEventListener("pointerdown", onPointer, { capture: true });
    window.removeEventListener("keydown", onKey, { capture: true });
  };
}
