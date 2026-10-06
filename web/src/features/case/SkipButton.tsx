import { SkipForward } from "lucide-react";

/** Props of {@link SkipButton}. */
export interface SkipButtonProps {
  /** Ends the flythrough at once. */
  readonly onSkip: () => void;
}

/**
 * Glass "Skip" button shown during the flythrough (Esc does the same).
 *
 * @returns The button.
 */
export function SkipButton({ onSkip }: SkipButtonProps) {
  return (
    <button
      type="button"
      className="case-btn case-glass case-skip"
      onClick={onSkip}
      aria-keyshortcuts="Escape"
    >
      Skip
      <SkipForward size={15} strokeWidth={1.75} nonScalingStroke aria-hidden="true" />
      <kbd className="case-skip__key" aria-hidden="true">
        Esc
      </kbd>
    </button>
  );
}
