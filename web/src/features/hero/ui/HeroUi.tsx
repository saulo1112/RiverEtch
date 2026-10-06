// The hero's UI layer: static placeholders (navigation, headline, calls to action, step strip and
// status chip) laid over the scene. Nothing here is wired to data, the wallet or the scan state.
import "@fontsource-variable/inter-tight";
import "@fontsource-variable/geist-mono";
import "./ui.css";

/** Props of {@link HeroUi}. */
export interface HeroUiProps {
  /** Id for the headline, which labels the hero section (`aria-labelledby`). */
  readonly titleId: string;
}

/**
 * Overlay on top of the hero scene. A direct child of the hero section, so it fills it.
 *
 * @returns The overlay.
 */
export function HeroUi({ titleId }: HeroUiProps) {
  return (
    <div className="hero-ui" data-title-id={titleId}>
      <main className="hero-ui__main" />
    </div>
  );
}
