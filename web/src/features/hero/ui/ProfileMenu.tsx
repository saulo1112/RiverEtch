import { focusForVisitor } from "../../ui/modality.ts";
import { UserRound } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState, type FocusEvent } from "react";
import { useAccount } from "wagmi";

import { WalletControl } from "../../wallet/WalletControl.tsx";
import { HEADER, PROFILE } from "./content.ts";

/** Props of {@link ProfileMenu}. */
export interface ProfileMenuProps {
  /** The overlay is hidden or fading out (a flight): the menu stays closed. */
  readonly leaving: boolean;
}

// Elements that take focus themselves when pressed.
const FOCUSABLE = "a[href], button, input, select, textarea, [tabindex]";

/**
 * The profile button and its menu: the simulated workspace user and the optional wallet. The
 * button's dot is grey without a wallet and blue with one. The menu is a non-modal dialog: it
 * takes focus when it opens, and Esc, a press outside or moving focus out of it closes it (Esc and
 * outside presses hand focus back to the button).
 *
 * @returns The profile button and, when open, its menu.
 */
export function ProfileMenu({ leaving }: ProfileMenuProps) {
  const [open, setOpen] = useState(false);
  const shown = open && !leaving;
  const { isConnected } = useAccount();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const statusId = useId();

  const close = useCallback((returnFocus: boolean) => {
    setOpen(false);
    if (returnFocus) {
      focusForVisitor(buttonRef.current);
    }
  }, []);

  useEffect(() => {
    if (!shown) {
      return undefined;
    }
    focusForVisitor(menuRef.current);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close(true);
      }
    };
    const onPointer = (event: PointerEvent) => {
      const target = event.target;
      if (
        !(target instanceof Node) ||
        menuRef.current?.contains(target) === true ||
        buttonRef.current?.contains(target) === true
      ) {
        return;
      }
      // A press on another control keeps the focus it gives; anywhere else, focus returns here.
      const onControl = target instanceof Element && target.closest(FOCUSABLE) !== null;
      close(!onControl);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [shown, close]);

  const onMenuBlur = (event: FocusEvent<HTMLDivElement>) => {
    const next = event.relatedTarget;
    // Null: the window lost focus, or a press is about to be handled by onPointer.
    if (
      next === null ||
      menuRef.current?.contains(next) === true ||
      buttonRef.current?.contains(next) === true
    ) {
      return;
    }
    setOpen(false);
  };

  return (
    <div className="hero-profile">
      <button
        ref={buttonRef}
        type="button"
        className="hero-profile__button"
        aria-label={HEADER.profile}
        aria-haspopup="dialog"
        aria-expanded={shown}
        aria-controls={shown ? menuId : undefined}
        aria-describedby={statusId}
        data-wallet={isConnected ? "connected" : "none"}
        onClick={() => {
          setOpen((value) => !value);
        }}
      >
        <UserRound size={18} strokeWidth={1.5} nonScalingStroke aria-hidden="true" />
        <span className="hero-profile__dot" aria-hidden="true" />
      </button>
      <span id={statusId} className="hero-ui__visually-hidden">
        {isConnected ? HEADER.walletConnected : HEADER.walletNotConnected}
      </span>
      {shown ? (
        <div
          ref={menuRef}
          id={menuId}
          className="hero-profile__menu hero-ui__glass"
          role="dialog"
          aria-label={PROFILE.label}
          tabIndex={-1}
          onBlur={onMenuBlur}
        >
          <div className="hero-profile__who">
            <span className="hero-profile__avatar" aria-hidden="true">
              <UserRound size={18} strokeWidth={1.5} nonScalingStroke />
            </span>
            <div className="hero-profile__identity">
              <p className="hero-profile__name">
                {PROFILE.name}
                <span className="hero-profile__badge">{PROFILE.testUser}</span>
              </p>
              <p className="hero-profile__role">{PROFILE.role}</p>
            </div>
          </div>
          <WalletControl
            variant="menu"
            onBeforeModal={() => {
              close(true);
            }}
          />
          <p className="hero-profile__note">{PROFILE.note}</p>
        </div>
      ) : null}
    </div>
  );
}
