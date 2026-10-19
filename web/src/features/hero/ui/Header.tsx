import { BRAND_PARTS, HEADER, WORDMARK_ACCENT } from "./content.ts";
import { ProfileMenu } from "./ProfileMenu.tsx";

/** Props of {@link Header}. */
export interface HeaderProps {
  /** The overlay is hidden or fading out (a flight): the profile menu closes. */
  readonly leaving: boolean;
}

/**
 * The hero's header: a transparent bar with the wordmark on the left and the profile button on the
 * right. No links: the hero is the entry of the demo workspace.
 *
 * @param props - The header's props.
 * @param props.leaving - The overlay is hidden or fading out.
 * @returns The page header.
 */
export function Header({ leaving }: HeaderProps) {
  const [river, etch] = BRAND_PARTS;
  return (
    <header className="hero-header">
      <a className="hero-header__brand" href="/" aria-label={HEADER.home}>
        <span className="hero-header__name">
          {river}
          {WORDMARK_ACCENT === "etch" ? (
            <span className="hero-header__accent">{etch}</span>
          ) : (
            <>
              <span className="hero-header__accent">{etch.slice(0, 1)}</span>
              {etch.slice(1)}
            </>
          )}
        </span>
      </a>
      <ProfileMenu leaving={leaving} />
    </header>
  );
}
