// The hero's UI layer over the scene: the header with the profile menu, and one screen at a time
// (the entry copy, or the demo analyst's cases), the bottom row and the "How it works" dialog.
import "@fontsource-variable/inter-tight";
import "@fontsource-variable/geist-mono";
import "../../../styles/tokens.css";
import "./ui.css";

import { useEffect, useRef, useState } from "react";

import { CasesPanel } from "./CasesPanel.tsx";
import { CASES } from "./content.ts";
import { Copy } from "./Copy.tsx";
import { Footer } from "./Footer.tsx";
import { Header } from "./Header.tsx";
import { HowItWorksDialog } from "./HowItWorksDialog.tsx";

/** Which screen the overlay shows. */
export type HeroScreen = "entry" | "cases";

/** Props of {@link HeroUi}. */
export interface HeroUiProps {
  /** Id for the visible screen's heading, which labels the hero section (`aria-labelledby`). */
  readonly titleId: string;
  /** The overlay is hidden or fading out (the flythrough either way) and takes no input. */
  readonly leaving?: boolean;
  /** "Open case": starts the flythrough. */
  readonly onExplore?: () => void;
  /** The pointer or the focus reached a control that leads to the case view. */
  readonly onWarmUp?: () => void;
  /** Focus "Open case" (when this turns true: back from the case view). */
  readonly focusExplore?: boolean;
  /** The screen to start on (read on mount only): the cases after the way back. */
  readonly initialScreen?: HeroScreen;
}

/**
 * Overlay on top of the hero scene. A direct child of the hero section, so it fills it. Moving
 * between screens moves focus (to the cases heading, or back to "Explore your cases") and is
 * announced politely.
 *
 * @returns The overlay.
 */
export function HeroUi({
  titleId,
  leaving = false,
  onExplore,
  onWarmUp,
  focusExplore = false,
  initialScreen = "entry",
}: HeroUiProps) {
  const [screen, setScreen] = useState<HeroScreen>(initialScreen);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const exploreRef = useRef<HTMLButtonElement>(null);
  const howItWorksRef = useRef<HTMLButtonElement>(null);
  const casesHeadingRef = useRef<HTMLHeadingElement>(null);
  const openCaseRef = useRef<HTMLButtonElement>(null);
  // Where focus goes once the next screen has rendered.
  const pendingFocus = useRef<HeroScreen | null>(null);

  useEffect(() => {
    const target = pendingFocus.current;
    pendingFocus.current = null;
    if (target === "cases") {
      casesHeadingRef.current?.focus({ preventScroll: true });
    } else if (target === "entry") {
      exploreRef.current?.focus({ preventScroll: true });
    }
  }, [screen]);

  // After the way back the overlay was inert until now, so focus moves here explicitly (an
  // autoFocus on mount would land on an inert button).
  useEffect(() => {
    if (focusExplore) {
      openCaseRef.current?.focus({ preventScroll: true });
    }
  }, [focusExplore]);

  const show = (next: HeroScreen) => {
    pendingFocus.current = next;
    setScreen(next);
    setAnnouncement(next === "cases" ? CASES.announceOpen : CASES.announceBack);
  };

  return (
    <div className="hero-ui" inert={leaving} data-screen={screen}>
      <Header leaving={leaving} />
      <main className="hero-ui__main">
        {screen === "entry" ? (
          <Copy
            titleId={titleId}
            onOpenCases={() => {
              show("cases");
            }}
            onHowItWorks={() => {
              setDialogOpen(true);
            }}
            onWarmUp={onWarmUp}
            exploreRef={exploreRef}
            howItWorksRef={howItWorksRef}
          />
        ) : (
          <CasesPanel
            titleId={titleId}
            headingRef={casesHeadingRef}
            openCaseRef={openCaseRef}
            onBack={() => {
              show("entry");
            }}
            onOpenCase={onExplore}
            onWarmUp={onWarmUp}
          />
        )}
        <Footer />
      </main>
      <HowItWorksDialog
        open={dialogOpen && !leaving}
        onClose={() => {
          setDialogOpen(false);
          howItWorksRef.current?.focus({ preventScroll: true });
        }}
      />
      <p className="hero-ui__visually-hidden" aria-live="polite">
        {announcement}
      </p>
    </div>
  );
}
