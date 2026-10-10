import { BRAND_NAME, HEADER } from "./content.ts";
import { Logo } from "./Logo.tsx";
import { ProfileMenu } from "./ProfileMenu.tsx";

/** Props of {@link Header}. */
export interface HeaderProps {
  /** The overlay is hidden or fading out (a flight): the profile menu closes. */
  readonly leaving: boolean;
}

/**
 * The hero's header: a transparent bar with the brand on the left and the profile button on the
 * right. No links: the hero is the entry of the demo workspace.
 *
 * @returns The page header.
 */
export function Header({ leaving }: HeaderProps) {
  return (
    <header className="hero-header">
      <a className="hero-header__brand" href="/" aria-label={HEADER.home}>
        <Logo />
        <span className="hero-header__name">{BRAND_NAME}</span>
      </a>
      <ProfileMenu leaving={leaving} />
    </header>
  );
}
