// Every string in the hero's UI layer, in one place. A value in FNU is claimed only where a gauge
// validated it, with its error, and a class where there is none; NDTI stays relative; nothing
// claims causes or proof of compliance.

/**
 * Product name, in the two parts the header's wordmark colors: changing them renames the product
 * in the UI and in the wallets. `web/index.html` repeats it in the page title.
 */
export const BRAND_PARTS = ["River", "Etch"] as const;
export const BRAND_NAME = BRAND_PARTS.join("");

/** Which letters of the wordmark wear the accent. */
export type WordmarkAccent = "etch" | "e";

/**
 * The header's wordmark: "etch" (A) colors "Etch", "e" (B) only its "E". Its size, weight and glow
 * are the `--wordmark-*` values in ui.css.
 */
export const WORDMARK_ACCENT = "etch" as WordmarkAccent;

/** Header: the brand link and the profile button. */
export const HEADER = {
  home: `${BRAND_NAME} home`,
  profile: "Profile menu",
  walletConnected: "Wallet connected",
  walletNotConnected: "No wallet connected",
} as const;

/** The simulated user of this demo workspace, as the profile menu shows it. */
export const PROFILE = {
  label: "Profile",
  name: "Demo analyst",
  role: "Environmental authority (simulated)",
  testUser: "Test user",
  note: "Test user for this demo. Connecting a wallet is optional and doesn't change permissions.",
} as const;

/**
 * Entry screen. The eyebrow items are written in sentence case and set in capitals by CSS, so
 * screen readers read words, not letters.
 */
export const COPY = {
  eyebrow: ["Free satellite images", "Stated error", "Sealed readings"],
  title: ["See the river.", "Verify the reading."],
  subtitle:
    "A measuring station sees one point of a river. Most of the river lies far from any station. RiverEtch reads the water from free satellite images, tells you how far off each reading can be, and seals it, so any later change would show.",
  // A button: it opens the cases screen.
  primary: { label: "Explore your cases" },
  // A button: it opens the "How it works" dialog.
  secondary: { label: "How it works" },
} as const;

/** One of the three indicators under the calls to action: a figure, what it counts, a detail. */
export interface Indicator {
  /** Stable key. */
  readonly id: "rivers" | "check" | "proofs";
  /** What the figure counts (the figure itself comes from the data where it is a count). */
  readonly label: string;
  /** One short line under it. */
  readonly description: string;
}

/** The three indicators, in reading order. "rivers" is counted from the transfer test. */
export const INDICATORS: readonly Indicator[] = [
  { id: "rivers", label: "rivers tested", description: "failures shown" },
  { id: "check", label: "click to check", description: "no wallet, no account" },
  {
    id: "proofs",
    label: "separate checks",
    description: "Ethereum, Bitcoin and a quantum-safe signature",
  },
];

/** Status chip: what this page is, until the daily run's status has been read. */
export const STATUS = "Demo workspace";

/**
 * The live record: the chip's words once the daily run's status is read, and its dialog. In the
 * product's words: what updates, when it last did, and where the proofs are; the run's own log
 * stays on GitHub.
 */
export const RUN_STATUS = {
  chipLive: (date: string) => `Live · updated ${date}`,
  open: "About this record",
  title: "A live record",
  lead: "Twice a day, RiverEtch reads the new satellite passes and seals every reading. The record's fingerprints are posted on Ethereum and timestamped on Bitcoin, so anyone can check them.",
  snapshot: "This version of the site shows the readings included when it was built.",
  lastUpdate: "Last update",
  newest: "Newest reading",
  newestValue: (place: string, date: string) => `${place}, pass of ${date}`,
  ethereum: "Posted on Ethereum (Sepolia)",
  block: (block: number) => `block ${String(block)}`,
  bitcoin: "Timestamped on Bitcoin",
  bitcoinBlock: (height: number, when: string | null) =>
    when === null ? `block ${String(height)}` : `block ${String(height)} (${when})`,
  notYet: "not yet",
  close: "Close",
  externalHint: "(opens in a new tab)",
} as const;

/**
 * The evidence strip under the copy column. The figures are counted from the reaches' committed
 * files (see evidence.ts); only the words are written here.
 */
export const EVIDENCE = {
  label: "The demo's records",
  sealed: (n: number) => (n === 1 ? "sealed reading" : "sealed readings"),
  anchored: "Their fingerprints on Ethereum",
  anchorHint: "(the public board's page on Etherscan, a test network, opens in a new tab)",
} as const;

/** Credits for the scene's data, shown under the strip. */
export const ATTRIBUTION = "Earth imagery: NASA Earth Observatory (Blue Marble).";

/** The cases screen: the pipeline's demo reaches. */
export const CASES = {
  heading: "Your cases",
  note: "Real passes from the pipeline, sealed and verifiable.",
  back: "Back",
  backLabel: "Back to the start",
  listLabel: "Cases",
  announceOpen: "Your cases.",
  announceBack: "Start screen.",
  externalHint: "(opens in a new tab)",
  card: {
    open: "Open case",
    previewLabel: "Open case:",
    imageAlt: "The landed case view: the river, its turbidity and the record panels.",
    realData: "Real data · 2026",
    levelHint: "Level from a locked test on years the model never saw",
    error: "typical error",
    lastPass: "Last pass",
    passes: "passes recorded in 2026",
  },
} as const;

/**
 * "How it works": six short chapters in plain English (one idea each). Every number shown is
 * computed from a committed file at build time (see how/); only the words live here. Technical
 * terms sit in `term` lines, set small, never in the main sentence.
 */
export const HOW_IT_WORKS = {
  title: "How it works",
  close: "Close",
  chaptersLabel: "Chapters",
  count: (k: number, n: number) => `${String(k)} of ${String(n)}`,
  back: "Back",
  next: "Next",
  chapters: [
    { id: "problem", short: "The problem", title: "A station measures one point of a river" },
    { id: "reads", short: "What it reads", title: "What the satellite reads" },
    { id: "fingerprint", short: "The fingerprint", title: "Every reading gets a fingerprint" },
    { id: "works", short: "Does it work?", title: "Does it work?" },
    { id: "try", short: "Try it", title: "Try it yourself" },
    { id: "limits", short: "Limits", title: "What it cannot do" },
  ],
  problem: {
    lead: "A measuring station sees one point of a river. Most of the river lies far from any station.",
    more: "RiverEtch reads the whole stretch from free satellite images, every few days, when there are no clouds.",
    chartTitle: (y: {
      year: number;
      low: number;
      lowSeen: number;
      high: number;
      highSeen: number;
    }) =>
      y.low > 0 && y.high > 0
        ? `In ${String(y.year)} the river ran low on ${String(y.low)} days and high on ${String(y.high)}. The satellite saw ${String(y.lowSeen)} of the low days and ${String(y.highSeen)} of the high ones clearly.`
        : y.low > 0
          ? `In ${String(y.year)} the river ran low on ${String(y.low)} days. The satellite saw it clearly on ${String(y.lowSeen)} of them.`
          : y.high > 0
            ? `In ${String(y.year)} the river ran high on ${String(y.high)} days. The satellite saw it clearly on ${String(y.highSeen)} of them.`
            : `In ${String(y.year)} the river never ran very low or very high.`,
    stationLabel: "Station",
    yearLabel: "Year",
    plotLabel: (station: string, year: number) => `${station}: daily flow in ${String(year)}`,
    hint: "Move over the chart to read any day. On a keyboard, focus the chart and use the arrow keys to step through the clear-view days.",
    flowAxis: "River flow, m³/s (log scale, so low flows stay visible)",
    lowLine: "Low-flow line",
    highLine: "High-flow line",
    seenExtreme: "Clear view on a low-flow or high-flow day",
    seenOther: "Clear view on another day",
    noValue: "No station value",
    lowDay: "Low-flow day",
    highDay: "High-flow day",
    normal: "Neither",
    seen: "Clear satellite view",
    notSeen: "No clear satellite view",
    source: (station: string, source: string, missing: number) =>
      `Flow: ${station}, ${source}${missing > 0 ? ` (no value on ${String(missing)} ${missing === 1 ? "day" : "days"}; the line breaks there)` : ""}. Satellite: Sentinel-2. The two lines mark the station's lowest and highest 10 % of days on record.`,
    tableCaption: (year: number) =>
      `Days in ${String(year)} with a clear satellite view, and the river's flow`,
    day: "Day",
    flow: "Flow (m³/s)",
    kind: "Low or high flow",
  },
  reads: {
    cards: [
      {
        title: "How muddy the water is",
        term: "Turbidity, in FNU",
        text: "It rises when rain washes soil into the river. Cloudy water can shelter germs from the disinfectants that make drinking water safe.",
        source: "USGS Water Science School, “Turbidity and Water”",
        url: "https://www.usgs.gov/special-topics/water-science-school/science/turbidity-and-water",
      },
      {
        title: "How warm the water is",
        term: "Water temperature, in °C",
        text: "Warm water holds less oxygen than cool water, and it can harm the life in the river.",
        source: "USGS Water Science School, “Temperature and Water”",
        url: "https://www.usgs.gov/special-topics/water-science-school/science/temperature-and-water",
      },
    ],
    stationTitle: "From the station, for context",
    stationText:
      "Flow and water level come from the river's measuring station. They are shown beside the satellite's reading. The satellite does not measure flow.",
  },
  fingerprint: {
    lead: "A fingerprint is a short code made from every number in a reading. Change one number, and the whole code changes.",
    demoTitle: "A real reading",
    loading: "Loading a real reading…",
    unavailable:
      "The reading could not be loaded here. Open a river and press “Verify this record” instead.",
    place: "Place",
    date: "Date",
    turbidity: "Turbidity",
    edit: "Type a new value, or press − or +",
    down: "Lower the turbidity by one step",
    up: "Raise the turbidity by one step",
    changed: (k: number, n: number) => `${String(k)} of ${String(n)} characters changed`,
    sealed: "Fingerprint when it was sealed",
    now: "Fingerprint now",
    matches: "Matches. This is the reading as it was sealed.",
    differs: "Does not match. The reading was changed.",
    reset: "Put the number back",
    technical:
      "The fingerprint is the SHA-256 of the reading's canonical JSON, recomputed in your browser.",
    boardsTitle: "Then it is posted where nobody can change it",
    boards: [
      {
        title: "On a public board",
        text: "The latest fingerprint of each list of readings goes on Ethereum. Nobody can edit or delete it.",
        term: "Ethereum Sepolia, a public test network",
      },
      {
        title: "On a second public board",
        text: "The same fingerprint is dated on Bitcoin. That needs no key at all.",
        term: "OpenTimestamps",
      },
      {
        title: "Signed with a quantum-safe lock",
        text: "RiverEtch also signs it with a lock that future quantum computers cannot break.",
        term: "ML-DSA-65 (FIPS 204)",
      },
    ],
  },
  works: {
    bigAbout: "about",
    bigUnit: "×",
    bigLabel: "smaller error than guessing the river's usual value",
    bigNote: (station: string, sat: string, guess: string) =>
      `At the middle station of the nine, half of the satellite's errors were under ${sat} %. Guessing the usual value gave ${guess} % (${station}).`,
    tally: (good: number, n: number) =>
      `${String(good)} of ${String(n)} stations beat guessing by a clear margin.`,
    viewLabel: "Which test to show",
    views: { never: "Rivers it never saw", own: "Its own river" },
    barsTitle: (view: "never" | "own", beat: number, n: number, fail: number) =>
      view === "never"
        ? `On rivers the model never saw, ${String(beat)} of ${String(n)} stations still beat guessing. ${String(fail)} failed.`
        : `Trained on its own river, the model beat guessing at ${String(beat)} of ${String(n)} stations. ${String(fail)} failed.`,
    satelliteNever: "Satellite, a model that never saw that river",
    satelliteOwn: "Satellite, a model trained on that river's earlier years",
    guess: "Guessing the river's usual value",
    tipSatellite: "Satellite:",
    tipGuess: "Guessing:",
    timesSmaller: (times: string) => `About ${times} times smaller error than guessing`,
    noGain: "No clear gain over guessing",
    worse: "Not better than guessing",
    passes: (n: number) => `${String(n)} test passes`,
    passesHead: "Test passes",
    unscored: (names: readonly string[]) =>
      `Not scored (too few test passes): ${names.join(", ")}.`,
    barsHint: "Move over a station, tap it or focus it to see its numbers.",
    fails: "fails",
    axis: "Typical error, % of the station's value",
    classLine: (k: number, n: number) =>
      `Where there is no station, RiverEtch shows a class only. On similar rivers it never saw, the class matched the station in ${String(k)} of ${String(n)} passes.`,
    source:
      "Each model was tested once, on years it had never seen (Dec 2023 to Sep 2026). Errors are medians.",
    tableCaption: "Each station: the satellite's typical error and guessing the usual value",
    station: "Station",
  },
  try: {
    lead: "Check a sealed reading yourself, then break it on purpose.",
    steps: [
      "Open a river",
      "Press “Verify this record”",
      "Tick “Change one number first”",
      "Press it again: the check fails",
    ],
    gauged: "Open a river with a station",
    gaugedNote: "Mississippi at Belle Chasse",
    ungauged: "Open a river with no station",
    ungaugedNote: "Mississippi at St. Joseph",
    tour: "Each river has a short tour, top left.",
  },
  limits: [
    { title: "Clouds", text: "Clouds hide about three passes in four." },
    {
      title: "No station, no number",
      text: "Where there is no station, it shows a class, never a number.",
    },
    {
      title: "Sealed is not the same as right",
      text: "A fingerprint shows that a reading was not changed. It does not show that the reading is right. The tests show how often it was right.",
    },
    {
      title: "Muddy is not polluted",
      text: "Muddy water is not the same as polluted water. It cannot see oxygen, metals or germs.",
    },
    {
      title: "Clear rivers",
      text: "On clear rivers, like the Connecticut, it did no better than guessing, so it shows no number there.",
    },
    {
      title: "A test network",
      text: "The first public board (Ethereum Sepolia) is a test network.",
    },
  ],
} as const;
