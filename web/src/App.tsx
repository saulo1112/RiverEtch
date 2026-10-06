import { useState } from "react";

import { CaseView } from "./features/case/CaseView.tsx";
import { ILLUSTRATIVE_CASE } from "./features/case/sample.ts";
import { Hero } from "./features/hero/Hero.tsx";

type View = "hero" | "case";

// Development shortcut: `?view=case` opens the case view directly.
const initialView: View =
  import.meta.env.DEV && new URLSearchParams(window.location.search).get("view") === "case"
    ? "case"
    : "hero";

/**
 * Application root: the landing hero, or the case view (development: `?view=case`).
 *
 * @returns The root UI of the dApp.
 */
export function App() {
  const [view, setView] = useState<View>(initialView);
  return view === "case" ? (
    <CaseView
      data={ILLUSTRATIVE_CASE}
      onBack={() => {
        setView("hero");
      }}
    />
  ) : (
    <Hero />
  );
}
