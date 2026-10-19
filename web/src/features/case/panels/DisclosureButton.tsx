import { ChevronDown } from "lucide-react";

/** Props of {@link DisclosureButton}. */
export interface DisclosureButtonProps {
  /** What it shows or hides (its accessible name; the state is `aria-expanded`). */
  readonly label: string;
  /** The details are shown. */
  readonly open: boolean;
  /** Id of the region it shows or hides. */
  readonly controls: string;
  readonly onToggle: (open: boolean) => void;
}

/**
 * The toggle on a panel's heading row that shows or hides the panel's details: a chevron that
 * turns over when they are shown. A native button, so Enter and Space work.
 *
 * @returns The button.
 */
export function DisclosureButton({ label, open, controls, onToggle }: DisclosureButtonProps) {
  return (
    <button
      type="button"
      className="case-disclosure"
      aria-expanded={open}
      aria-controls={controls}
      title={label}
      onClick={() => {
        onToggle(!open);
      }}
    >
      <ChevronDown size={16} strokeWidth={1.9} aria-hidden="true" />
      <span className="case-visually-hidden">{label}</span>
    </button>
  );
}
