import { useId } from "react";

/** Props of {@link Logo}. */
export interface LogoProps {
  /** Rendered size in CSS pixels (the mark is square). */
  readonly size?: number;
}

/**
 * Placeholder brand mark: an orbit ring with a satellite on it, in `currentColor`. The view box is
 * tight to the ring's outer edge, so the ink starts exactly at the element's left edge.
 *
 * @returns The decorative SVG mark.
 */
export function Logo({ size = 20 }: LogoProps) {
  const maskId = useId();
  return (
    <svg
      className="hero-logo"
      width={size}
      height={size}
      viewBox="0 0 20 20"
      aria-hidden="true"
      focusable="false"
    >
      <mask id={maskId}>
        <rect width="20" height="20" fill="#fff" />
        {/* Gap in the ring around the satellite. */}
        <circle cx="16.45" cy="3.55" r="3.9" fill="#000" />
      </mask>
      <circle
        cx="10"
        cy="10"
        r="9.125"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        mask={`url(#${maskId})`}
      />
      <circle cx="16.45" cy="3.55" r="2.25" fill="currentColor" />
    </svg>
  );
}
