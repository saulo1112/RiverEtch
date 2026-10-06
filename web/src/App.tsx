import { CaseView } from "./features/case/CaseView.tsx";
import { ILLUSTRATIVE_CASE } from "./features/case/sample.ts";
import { Hero } from "./features/hero/Hero.tsx";

// Development shortcut: `?view=case` opens the case view directly.
const openCaseView =
  import.meta.env.DEV && new URLSearchParams(window.location.search).get("view") === "case";

/**
 * Application root: the landing hero (or, in development, the case view with `?view=case`).
 *
 * @returns The root UI of the dApp.
 */
export function App() {
  return openCaseView ? <CaseView data={ILLUSTRATIVE_CASE} /> : <Hero />;
}
