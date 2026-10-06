import { Wallet } from "lucide-react";

import { BRAND_NAME, NAV, NAV_ITEMS } from "./content.ts";
import { Logo } from "./Logo.tsx";

/**
 * Floating glass navigation: brand, section links and a wallet placeholder (not wired).
 *
 * @returns The primary navigation.
 */
export function Nav() {
  return (
    <nav className="hero-nav hero-ui__glass" aria-label={NAV.label}>
      <a className="hero-nav__brand" href="/" aria-label={NAV.home}>
        <Logo />
        <span className="hero-nav__name">{BRAND_NAME}</span>
      </a>
      <ul className="hero-nav__links">
        {NAV_ITEMS.map((item) => (
          <li key={item.label}>
            <a
              className="hero-nav__link"
              href={item.href}
              {...(item.external === true ? { target: "_blank", rel: "noopener noreferrer" } : {})}
            >
              {item.label}
              {item.external === true ? (
                <span className="hero-ui__visually-hidden"> {NAV.externalHint}</span>
              ) : null}
            </a>
          </li>
        ))}
      </ul>
      <button type="button" className="hero-btn hero-btn--ghost hero-nav__wallet">
        <Wallet size={16} strokeWidth={1.5} nonScalingStroke aria-hidden="true" />
        {NAV.wallet}
      </button>
    </nav>
  );
}
