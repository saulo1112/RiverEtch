// Every string of the case view, and the formatters its panels share. A value in FNU appears only
// with its level, its interval and the error its locked test measured; NDTI stays relative.
import type { Level } from "../reaches/types.ts";

// The locked tests' years (preregistration.md, "Splits": 2023-12-01..2026-09-30, for turbidity
// and water temperature alike).
export const LOCKED_TEST = "Dec 2023–Sep 2026";

/** Labels of the case view. */
export const CASE_COPY = {
  back: "Back to your cases",
  caseDetails: "Case details",
  pipelineChip: "Pipeline records · 2026",
  liveChip: "Live data · the daily run's published copy",
  snapshotChip: "Snapshot bundled with this build",
  scenePrefix: "Sentinel-2 pass",
  turbidity: "Turbidity at the station",
  interval: "90 % interval",
  gaugeAt: "USGS station when the satellite passed",
  gaugeNone: "no station value when the satellite passed",
  gaugeLink: "Station page (USGS)",
  noValue: "No value for this pass",
  rangeWithoutLevel:
    "The estimate fell in a range the locked test did not rate, so no value is published.",
  // How to read a value: its range, how far off it tends to be, and which way it leans.
  reading: {
    expectedRange: "Expected range",
    rangeHelpLabel: "About the expected range",
    rangeHelp: (k: number, n: number) =>
      `We expect the measured value to fall inside this range about 9 times out of 10; in testing it did ${String(k)} of ${String(n)} times.`,
    reliabilityTitle: "How far off it tends to be",
    lessIsBetter: "less is better",
    reliabilityHelpLabel: "About how far off it tends to be",
    satellite: "Satellite estimate",
    baseline: "Guess the river's usual value",
    baselineHelp:
      "The baseline is the error you would get by always guessing the median of the river's past values, with no satellite.",
    unitsHelp:
      "Turbidity runs from a few FNU to hundreds, so an error of 5 FNU is large at 10 FNU and small at 300: it is given as a share of the value. A degree means the same in any season, so temperature errors are in °C.",
    median: (n: number, mdsa: string) =>
      `In ${String(n)} test passes the model never saw, half of the errors were smaller than ${mdsa} %.`,
    mean: (n: number, mae: string) =>
      `In ${String(n)} test passes the model never saw, the errors averaged ${mae} °C.`,
    times: (r: string) => `About ${r} times smaller error than guessing the usual value.`,
    noGain: "No clear gain over guessing the usual value.",
    worse: "Not better than guessing the usual value.",
    tileMedian: (mdsa: string, n: number) =>
      `Half of test errors under ${mdsa} % (${String(n)} passes, ${LOCKED_TEST})`,
    tileMean: (mae: string, n: number) =>
      `Test errors averaged ${mae} °C (${String(n)} passes, ${LOCKED_TEST})`,
    leanWarm: (d: string) => `tends to read ${d} °C warm`,
    leanCold: (d: string) => `tends to read ${d} °C cold`,
    leanHigh: (p: string) => `tends to read about ${p} % high`,
    leanLow: (p: string) => `tends to read about ${p} % low`,
    leanNone: "no clear tendency to read high or low",
  },
  // What each level lets a reader do with the number (preregistration v5, levels).
  levelHelpLabel: "About this level",
  levelHelp: {
    validated:
      "Passed the locked test with a clear margin over guessing the usual value, on at least 20 passes in two years, with an honest range. You can cite the value with its range.",
    estimated:
      "Beat guessing the usual value under looser limits. Use the value with its range, and confirm it against the station when it matters.",
    estimatedCapped:
      "Met every validated threshold, but against a station whose values are still provisional, so it is capped at estimated.",
    indicative:
      "Follows the river's rises and falls, but not its level. Read it as low, medium or high, never as a number.",
    unvalidated:
      "No station measures this reach, so the satellite's reading is the only one here. The class comes from a model that never saw this reach; how far off it tends to be was measured on similar rivers it never saw either. Read it as a turbidity range in FNU, never as a number.",
    none: "Did not pass the locked test. Only the relative index is shown.",
  },
  // A reach with no gauge outside the region the model was tested in
  // (preregistration-outside-us.md): the same class, and no error figure of any kind.
  levelHelpOutside:
    "No station measures this reach, and the model was only ever tested on US rivers, so no error estimate exists here. Read the class as a turbidity range in FNU, never as a number, and not as checked.",
  // A reach with no gauge (preregistration-transfer.md, section 5): a class only, beside the
  // expected error that the test on rivers the model never saw measured; never a value.
  ungauged: {
    turbidity: "Turbidity class",
    classes: {
      under_15: "Under 15 FNU",
      "15_to_30": "15 to 30 FNU",
      under_30: "Under 30 FNU",
      "30_to_100": "30 to 100 FNU",
      "30_to_50": "30 to 50 FNU",
      "50_to_100": "50 to 100 FNU",
      "100_and_over": "100 FNU and over",
    },
    label: "Unvalidated: expected error from the transfer test",
    // The card's own label, as preregistration-outside-us.md fixes it (a test compares the two).
    outsideLabel: "Outside the tested region. No error estimate.",
    noClass: "No class for this pass",
    errorTitle: "How far off it tends to be, on rivers it never saw",
    agreement: (k: number, n: number) =>
      `In ${String(k)} of ${String(n)} test passes on rivers it never saw, the class matched the station.`,
    median: (mdsa: string, sites: number) =>
      `Half of those estimates were off by less than ${mdsa} % of the station's value (${String(sites)} sediment-carrying rivers like this one).`,
    baselineNote:
      "With no station here there is no usual value to compare with; each river's comparison is under Accuracy.",
    trainedOn:
      "The model never saw this reach. It did learn from two other Mississippi stations, at Cape Girardeau (upstream) and Belle Chasse (downstream).",
    window: "Reading spot (no station)",
    legendWindow: "The reading spot (no station here: a class only)",
    mapCaption: "No station here",
    chartKey: "Each pass's turbidity class in FNU (the height means the class only)",
    noGauge: "No station on this reach, so nothing here is scored against one.",
    // The pass's turbidity index against the river's own past passes (rule D0), on the card.
    ownPast: "Against this river's own past",
    ownPastHelpLabel: "About the river's own past",
    ownPastHelp: (n: number, from: string, to: string) =>
      `RiverEtch compares each pass's turbidity index (NDTI) with ${String(n)} earlier clear passes of this reach, from ${from} to ${to}. It needs no station: it says whether the water looks as usual for this river, muddier or clearer.`,
    ownPastWords: { usual: "Usual", high: "Muddier than usual", low: "Clearer than usual" },
    // Published measurements beside a reach (docs/water-quality/published/<reach>.json).
    published: {
      title: "Measured by others",
      helpLabel: "About these measurements",
      every: (v: string, unit: string) => `${v} ${unit} in every sample`,
      median: (v: string, unit: string, lo: string, hi: string) =>
        `median ${v} ${unit}, from ${lo} to ${hi}`,
      span: (lo: string, hi: string, unit: string) => `${lo} to ${hi} ${unit}`,
      away: (km: string, direction: string) => ` (${km} km ${direction})`,
      inLine: (cls: string) =>
        `Its class here, ${cls.charAt(0).toLowerCase()}${cls.slice(1)}, is in line with them.`,
      caveat:
        "Other years and another unit (NTU): a plausibility check, looked up after seeing the result, not a test.",
    },
    // Beside the class agreement once the reach has four classes (preregistration-four-classes.md).
    baseline: (k: number, n: number) =>
      `Always guessing the most common class matched ${String(k)} of ${String(n)}, a comparison decided after seeing the result.`,
  },
  // The guided tour: eight steps, each pointing at a control that exists on the case.
  tour: {
    open: "Tour",
    openLabel: "Take the guided tour of this case",
    bar: "Case navigation",
    count: (k: number, n: number) => `${String(k)} of ${String(n)}`,
    skip: "Skip tour",
    back: "Back",
    next: "Next",
    finish: "Finish",
    summaryTitle: "One pass of the satellite",
    summary:
      "One clear Sentinel-2 pass: the turbidity at the station spot, in FNU, with the range the station's value should fall in 9 times out of 10.",
    summaryUngauged:
      "One clear Sentinel-2 pass. No station measures this reach, so it shows a turbidity range in FNU, never a value, beside the error measured on rivers the model never saw.",
    summaryOutside:
      "One clear Sentinel-2 pass. No station measures this reach, and the model was only tested on US rivers, so it shows a turbidity range in FNU with no error estimate.",
    trustTitle: "What it is worth, and what protects it",
    trust:
      "The level says how far the model was tested; the (?) explains it. Sealed: the record's SHA-256 is fixed. Anchored: its ledger line is stored on a public chain.",
    verifyTitle: "Check it yourself",
    verify:
      "Your browser recomputes the seal, walks the ledger and checks the model card, then reads the anchor on Sepolia, the Bitcoin timestamp and the post-quantum signature. No wallet needed.",
    alterTitle: "Try to change it",
    alter:
      "Tick this and type another number (or pick another class), then verify again: the seal no longer matches. Put the sealed value back and it matches again. Nothing leaves your browser.",
    layersTitle: "The map is relative",
    layers:
      "NDTI per pixel, compared with this reach's own passes. It has no unit and is not validated: only the amber spot carries a value or a class.",
    tabsTitle: "The year, pass by pass",
    tabs: "The tabs hold the year's passes beside the station, the station's own readings and climate record, and the track record of readings sealed before the station's value was read.",
    tabsUngauged:
      "The tabs hold the year's passes by class, the turbidity index against the river's own past, and the image in detail. With no station there is no track record: nothing here is scored.",
    accuracyTitle: "Where it works",
    accuracy:
      "Every station it was tested on: where the satellite beats guessing the river's usual value, and the few where it does not.",
    neverTitle: "Rivers it never saw",
    never:
      "Every river tested, scored by a model that never saw it: the error to expect where there is no station.",
    neverOutside:
      "Every river tested, failures included, all of them in the US. This reach lies outside that region, so none of these errors applies to it.",
    endTitle: "That is the record",
    end: "Sealing proves a number was not changed; it does not prove it was right. The tests show how often it was right.",
  },
  trust: {
    label: "Record status",
    sealed: "Sealed",
    anchored: (date: string) => `Anchored ${date}`,
    checking: "Checking the anchor…",
    pending: "Recorded after the last anchor",
    mismatch: "No longer matches its anchor",
    unavailable: "Anchor not readable right now",
  },
  // Three kinds of number, each with its own mark and words, never colour alone.
  kinds: {
    gauge: "Station · measured",
    satellite: "Satellite · estimated",
    history: "History · computed",
    provisional: "Provisional",
    provisionalHelp:
      "Published by the USGS within minutes of the reading. It may still be revised.",
    approved: "Approved",
    approvedHelp: "Reviewed and approved by the USGS.",
  },
  record: {
    title: "Record",
    // Why a reader would verify a record the site already calls sealed.
    whyLabel: "Why verify a record?",
    why: "The site says each record is sealed; this lets you check that without trusting RiverEtch. Your browser recomputes the record's fingerprint, finds it in the reach's ledger and reads the ledger's fingerprint on Ethereum, posted when it was sealed. If anyone had changed a past reading since, RiverEtch included, the fingerprints would no longer match.",
    details: "Record details",
    ofPass: "Sentinel-2 pass",
    ofThermal: "water temperature",
    scene: "Scene",
    images: "Sentinel-2 images",
    landsatImages: "Landsat images",
    processing: "Processing",
    thermalProcessing: "Collection 2 Level-2 · band 10 surface temperature",
    window: "Station spot",
    waterPixels: "water pixels",
    code: "Code",
    card: "Model card",
    seal: "Record SHA-256",
    replaces: "Replaces",
    replacesNote: "read again with four classes; still in the ledger",
    verify: "Verify this record",
    verifying: "Verifying…",
    alter: "Change one number first",
    // The field "Change one number first" opens: the record's estimate, or its class.
    fieldValue: (unit: string) => `Turbidity estimate (${unit})`,
    fieldTemperature: (unit: string) => `Water temperature (${unit})`,
    fieldClass: "Turbidity class",
    fieldIndex: "Turbidity index downstream (NDTI)",
    sealedAs: (value: string) => `Sealed as ${value}. Change it, then verify.`,
    notNumber: "Type a number, such as 12.5.",
    unchanged: "Same as the sealed value: nothing changed, so the seal still matches.",
    download: "Download the record (JSON)",
    sealed: "Its content matches its seal (SHA-256)",
    broken: "Its content no longer matches its seal",
    inLedger: "Listed in the reach's ledger",
    notInLedger: "Not found in the ledger",
    chain: "Ledger chain intact",
    chainBroken: "Ledger chain broken",
    lines: "lines",
    cardOk: "Model card matches the hash the record names",
    cardBad: "Model card does not match the hash the record names",
    altered: "Changed in memory",
    // "Check a file you were sent": a record (JSON) or series (CSV) against the sealed records.
    checkFile: "Check a file you were sent",
    checkFileHint: "A record (JSON) or series (CSV). Checked in your browser; nothing is uploaded.",
    checkingFile: "Checking the file…",
    file: {
      identical: (date: string) => `Identical to the record sealed for the pass of ${date}`,
      notIdentical: (date: string) => `Not the record sealed for the pass of ${date}`,
      inLedger: "Its fingerprint is a line of this reach's ledger",
      notInLedger:
        "Its fingerprint is in no line of this reach's ledger: RiverEtch never sealed it",
      selfBroken: "Its content no longer matches the fingerprint it states",
      change: (what: string, sealed: string, given: string) =>
        `${what}: sealed ${sealed}, in the file ${given}`,
      seriesSame: (n: number) => `All ${String(n)} rows match the sealed records`,
      seriesChanged: (k: number, n: number) =>
        `${String(k)} of ${String(n)} rows differ from the sealed records`,
      unsealed: "its fingerprint is in no ledger line",
      unknown: (k: number) =>
        `${String(k)} ${k === 1 ? "row names" : "rows name"} no pass of this reach`,
      more: (k: number) => `and ${String(k)} more`,
      otherReach: (site: string) =>
        `This is a record of another reach (${site}): open its case to check it.`,
      unreadable: "This is not a RiverEtch record or series file.",
      failed: "The file could not be read.",
    },
    // A changed value, as a reader names it.
    fields: {
      "estimates[0].value": "turbidity estimate",
      "estimates[0].fnuClass": "turbidity class",
      "estimates[0].level": "level",
      "estimates[0].interval.low": "range, low end",
      "estimates[0].interval.high": "range, high end",
      "estimate.value": "water temperature",
      "indices.ndti.upstream": "turbidity index upstream",
      "indices.ndti.downstream": "turbidity index downstream",
      date: "date",
      level: "level",
      turbidity_fnu: "turbidity",
      turbidity_class: "turbidity class",
      interval90_low: "range, low end",
      interval90_high: "range, high end",
      abstain_reason: "why there is no reading",
      ndti_upstream: "turbidity index upstream",
      ndti_downstream: "turbidity index downstream",
    } as Readonly<Record<string, string>>,
    notAnchored: "Not anchored on a public chain yet: the seal and the ledger are checked here.",
    anchoredHint:
      "Each ledger's last line is anchored on Ethereum (Sepolia) as a public timestamp.",
    contract: "Anchor contract",
    chainAnchored: (date: string, block: number) =>
      `Ledger anchored on Sepolia on ${date} (block ${String(block)})`,
    chainPending: "Recorded after the last anchor on Sepolia: not anchored yet",
    chainMismatch: "The ledger no longer matches its anchor on Sepolia",
    chainUnavailable: "The anchor on Sepolia could not be read",
    viaWallet: "Read through your own wallet's connection to Sepolia",
    viaPublic: "Read through a public Sepolia node (connect a wallet to read it through your own)",
    anchorAction: "Anchor this reach's ledgers on Sepolia",
    anchoring: "Waiting for the wallet and the block…",
    anchoredTx: (ledgers: number) =>
      `${String(ledgers)} ${ledgers === 1 ? "ledger" : "ledgers"} anchored · view the transaction`,
    upToDate: "The ledgers are already anchored up to their last line.",
    anchorFailed: "The anchor failed or was rejected in the wallet.",
    failed: "The record could not be checked.",
  },
  legendTitle: "NDTI per pixel (relative)",
  legendLow: "Low",
  legendHigh: "High",
  legendRange: "within this reach's 2026 passes",
  legendPhoto: "True color of this pass",
  legendPhotoNote: "Sentinel-2 bands 4, 3 and 2 (red, green, blue), brightened as viewers do.",
  noData: "Cloud, glint or no data on this pass",
  window: "The station spot (where turbidity is estimated)",
  timelineTitle: "Turbidity, 2026",
  timelineSatellite: "Satellite estimate (FNU) and its 90 % interval",
  timelineGauge: "USGS station when the satellite passed",
  timelineNoValue: "No reading (cloud, glare or out of range)",
  timelineHint: "Select a pass to see its map and record.",
  tools: {
    label: "Map tools",
    layer: "What the river shows",
    ndti: "NDTI",
    photo: "True color",
    none: "Off",
    opacity: "Layer opacity",
    layers: "Layers",
    overlays: "Overlays",
    outline: "River corridor",
    window: "Station spot",
    windowUngauged: "Reading spot",
    terrain: "3D terrain",
    compare: "Compare",
    compareWith: "Compare the selected pass with",
    compareOff: "No comparison",
    compareHint: "Drag the split on the map to sweep between the two passes.",
    export: "Export",
    exportCsv: "Turbidity series (CSV)",
    exportGeometry: "Reach geometry (GeoJSON)",
    exportLedger: "Ledger (JSONL)",
    exportCard: "Model card (JSON)",
  },
  controls: {
    zoomIn: "Zoom in",
    zoomOut: "Zoom out",
    north: "Reset the view",
    view3d: "3D",
    view2d: "2D",
  },
  inspector: {
    ndti: "NDTI",
    relative: "relative",
    unusable: "Unusable on this pass",
    km: "km",
    of: "of",
  },
  tabs: {
    quality: "Water quality",
    series: "Turbidity, 2026",
    thermal: "Water temperature",
    climate: "Climate",
    pass: "Image details",
    scoreboard: "Track record",
    rivers: "Accuracy",
  },
  // Where the satellite works and where it does not: every station tested, from the committed
  // results, the ones it does not beat guessing the usual value on included.
  rivers: {
    summary: (k: number, n: number, median: string) =>
      `The satellite passed its locked test (${LOCKED_TEST}) at ${String(k)} of the ${String(n)} stations rated; across them, half of its errors were under ${median} %. The two demo rivers with a station are the best two.`,
    summaryNever: (k: number, n: number) =>
      `Scored once by a model that never saw the river (20 Oct 2026), it still passed at ${String(k)} of ${String(n)} stations: the error to expect where there is no station.`,
    outside:
      "All of these stations are in the US. This reach lies outside that region, so none of these errors applies to it.",
    works: (k: number) => `Where it works · ${String(k)} stations`,
    notRecommended: (k: number) => `Not recommended on these rivers · ${String(k)}`,
    notNote: "it did not beat guessing the usual value, so RiverEtch shows no number there",
    notNoteNever: "a model that never saw them did not beat guessing the usual value",
    thin: "Too few test passes to judge",
    tableCaption: "Every evaluated station's test, lowest error first",
    columns: {
      river: "River (USGS station)",
      level: "Level",
      satellite: "Satellite error",
      baseline: "Guess the usual value",
      passes: "Test passes",
    },
    errorHelpLabel: "About the errors",
    errorHelp:
      "Half of the locked-test errors were smaller than this share of the value. Guessing the usual value means always guessing the median of the river's past values, with no satellite.",
    demo: "demo reach",
    thisCase: "this case",
    insufficient: "Too few test passes",
    gain: (r: string) => `${r} times smaller`,
    noGain: "no clear gain",
    worse: "not better than guessing",
    inside: (k: number) => `${String(k)} inside the range`,
    otherMedian: (v: string) => `other rivers' median: ${v} %`,
    // Display names of the gauges, as the report's table writes them.
    names: {
      "USGS-07374525": "Mississippi at Belle Chasse",
      "USGS-06805500": "Platte at Louisville",
      "USGS-07381600": "Atchafalaya at Morgan City",
      "USGS-03216070": "Ohio at Ironton",
      "USGS-07020850": "Mississippi at Cape Girardeau",
      "USGS-11337190": "San Joaquin at Jersey Point",
      "USGS-01193050": "Connecticut at Middle Haddam",
      "USGS-14211720": "Willamette at Portland",
      "USGS-14144700": "Columbia at Vancouver",
      "USGS-14246900": "Columbia at Port Westward",
      "USGS-06934500": "Missouri at Hermann",
    } as Readonly<Record<string, string>>,
  },
  // The track record (docs/water-quality/prospective.md): counts, never percentages, until there
  // are 20 passes; every count says whether it was sealed before the station was read.
  scoreboard: {
    caption:
      "How many station values fell inside the expected range. Counts, not percentages, until there are 20 passes.",
    prospective: "Sealed before the station was read",
    prospectiveHelpLabel: "About passes sealed in advance",
    prospectiveHelp:
      "The model and the scoring rule were anchored on Sepolia before the satellite took the image, and the estimate was sealed and anchored before RiverEtch read the station. That proves the estimate was not changed after the reading, not that the reading was unknown: the USGS publishes provisional values within minutes.",
    since: (date: string) => `since ${date}`,
    notStarted: "Starts when the scoring rule is anchored on Sepolia.",
    empty: (date: string) =>
      `Waiting for the first clear pass since ${date}. Each new pass is sealed and anchored before the station's value is read, then scored here.`,
    retrospective: "Checked after the station's value was public",
    retrospectiveHelpLabel: "About passes checked after the fact",
    retrospectiveHelp:
      "Sealed after the station's value was public. It shows how the model behaves, not a claim made in advance.",
    passes2026: "This year's passes",
    passes2026Note: "recent station values may be revised",
    lockbox: "Locked test",
    lockboxNote: `passes the model never saw, ${LOCKED_TEST}`,
    count: (k: number, n: number) => `${String(k)} of ${String(n)}`,
    inside: "inside",
    turbidity: "Turbidity",
    temperature: "Water temperature",
    results: {
      inside: "Inside the range",
      outside: "Outside the range",
      pending: "No station value yet",
      none: "No station value",
      abstained: "No estimate (abstained)",
      noRange: "No expected range",
    },
    approvedLater: (value: string) => `Approved later: ${value}`,
    columns: { pass: "Pass", estimate: "Estimate", gauge: "Station", result: "Result" },
  },
  climate: {
    lead: "Continued warming is projected to make wet and dry extremes more severe",
    cite: "IPCC AR6, SPM B.3.1",
    citeUrl: "https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/",
    note: "Below, the station's own daily record: measurements, not a trend or an attribution.",
    measures: { peak: "Annual peak", low: "7-day low", warm: "Warmest day" },
    facts: {
      peak: "Highest annual peak",
      low: "Lowest 7-day flow",
      warm: "Warmest summer day",
    },
    span: (years: number, what: "years" | "summers") => `in ${String(years)} ${what}`,
    since: (year: string, station: string) => `${station} · record since ${year}`,
    weekTo: "week to",
    toDate: "so far, not ranked",
    soFar: "so far",
    incomplete: "incomplete year, not ranked",
    provisional: "includes provisional values",
    keyTop: "Three most extreme years",
    keyToDate: "This year so far",
    chart: (measure: string, station: string) => `${measure} per year at ${station}`,
    table: "Every year of the station's record",
    // Extreme days (rule v1, docs/water-quality/prospective.md): counts and ranks from the gauge.
    views: { label: "What the climate tab shows", values: "Yearly extremes", days: "Extreme days" },
    kinds: { low: "Low-flow days", high: "High-flow days", warm: "Warm-water days" },
    kindWords: { low: "low-flow days", high: "high-flow days", warm: "warm-water days" },
    mostIn: (kind: string, years: number, what: "years" | "summers") =>
      `Most ${kind} in ${String(years)} ${what}`,
    days: (n: number) => `${String(n)} days`,
    dayUnit: "days",
    seen: (first: number, last: number, k: string, n: string, kind: string) =>
      `The satellite saw ${k} of ${n} ${kind} in ${String(first)}–${String(last)}`,
    seenOthers: (k: string, n: string) => ` (other days: ${k} of ${n})`,
    seenYear: (k: number, n: number) => `seen by the satellite on ${String(k)} of ${String(n)}`,
    notEnough: (k: number, n: number, min: number) =>
      `Not enough extreme days to judge the error on them: ${String(k)} of ${String(n)} test passes; ${String(min)} are needed.`,
    enough: (k: number, n: number) => `${String(k)} of ${String(n)} test passes fell on such days.`,
    definitionLabel: "About extreme days",
    definition: {
      low: (value: string, unit: string, first: string) =>
        `A day whose mean flow is at or below ${value} ${unit}: the lowest tenth of this station's approved days from ${first} to 2025.`,
      high: (value: string, unit: string, first: string) =>
        `A day whose mean flow is at or above ${value} ${unit}: the highest tenth of this station's approved days from ${first} to 2025.`,
      warm: (value: string, unit: string, first: string) =>
        `A June–September day whose mean water temperature is at or above ${value} ${unit}: the warmest tenth of this station's approved summer days from ${first} to 2025.`,
    },
    definitionNote:
      "Counted from the station's own record, never from the satellite, as the scoring rule defines them; no error on such days had been computed when it was written.",
    tableDays: "Extreme days in every year of the station's record",
  },
  thermal: {
    title: "Water temperature",
    satellite: "Landsat estimate (°C) and its 90 % interval",
    gauge: "USGS station when Landsat passed",
    upstreamGauge: (name: string) => `USGS station at ${name} (where it was validated)`,
    upstreamNote: (name: string) =>
      `Validated at ${name}, the nearest station on the river that measures temperature.`,
    // The dashed line: the Sentinel-2 pass the map and the other tabs show (Landsat passes on
    // other days); the lit dot: the Landsat pass whose record is open.
    cursor: "Day shown on the map",
    picked: "Selected Landsat pass",
    hint: "Select a Landsat pass to see its record.",
    pixels: "water pixels at the station spot",
    lead: "Locked test",
    error: "mean error",
    on: "on",
    overpasses: "overpasses",
    baseline: "day-of-year average",
  },
  quality: {
    satellite: "Estimated from the satellite",
    // What every tile's small line spans, said once; a station value's approval, said once.
    satelliteLines: "each line: this year's passes",
    gauge: "Measured by the USGS station",
    provisional: "recent values may be revised",
    provisionalLong:
      "The USGS publishes a station's values within minutes and may still revise the recent ones after review.",
    turbidity: "Turbidity",
    temperature: "Water temperature",
    sentinel: "Sentinel-2",
    landsat: "Landsat 8/9",
    validatedAt: "validated at",
    noLandsat: "No clear Landsat pass within 16 days",
    // A reach with no station: the pass's turbidity index against the reach's own past passes
    // (rule D0, sealed in every record).
    own: "Turbidity index vs its own past",
    ownSource: "Sentinel-2 · NDTI",
    usual: "Usual",
    high: "Muddier than usual",
    low: "Clearer than usual",
    ownDetail: (up: string, down: string, n: number, from: string, to: string) =>
      `${up} upstream and ${down} downstream, in spreads from usual, against ${String(n)} passes from ${from} to ${to}. Unusual from 3.`,
    ownDetailShort: (up: string, down: string) =>
      `${up} upstream and ${down} downstream, in spreads from usual. Unusual from 3.`,
    ownNone: "No index for this pass",
  },
  context: {
    title: "Measured by the USGS station when the satellite passed",
    none: "The station reported no value at this pass.",
    provisional: "Provisional data, subject to revision by the USGS.",
    provisionalShort: "provisional",
    approvedShort: "approved",
    names: {
      "00060": "River flow",
      "00065": "Water level",
      "00010": "Water temperature",
      "00300": "Dissolved oxygen",
      "00095": "Specific conductance",
      "00630": "Nitrate + nitrite (N)",
    } as Readonly<Record<string, string>>,
  },
  play: { play: "Play 2026", pause: "Pause", previous: "Previous pass", next: "Next pass" },
  profile: {
    title: "NDTI along the river, upstream to downstream",
    unusable: "unusable stretch",
    hint: "Hover the profile to find the place on the river.",
  },
  pass: {
    views: "What to show for this pass",
    stats: "Statistics",
    profile: "Along the river",
    water: "Water pixels in the corridor",
    usable: "Usable on this pass",
    clouded: "Lost to cloud, glint or no data",
    percentiles: "NDTI (10th · median · 90th percentile)",
    histogram: "Distribution of the pass's NDTI",
  },
  compare: { left: "Selected", right: "Compared" },
  verify: {
    title: "Verifying the record",
    step1: "Canonical content",
    step1Note: "Keys sorted, no spaces, numbers as written; the seal itself left out.",
    step2: "SHA-256 of the content",
    stated: "Sealed",
    computed: "Recomputed",
    step3: "Place in the ledger",
    step3Note:
      "Each line names the SHA-256 of the line before: changing one breaks every link after it.",
    step4: "Model card",
    step5: "Anchored on a public chain",
    step5Note:
      "The SHA-256 of a ledger line, stored on Ethereum at a block's time, commits to every line above it.",
    step6: "Timestamped on Bitcoin",
    step6Note:
      "An OpenTimestamps proof that a ledger head covering this record existed by a Bitcoin block, checked against two public block explorers. It needs no key: only hashes.",
    bitcoinConfirmed: (date: string, height: number, lines: number) =>
      `In Bitcoin block ${String(height)} (${date}), with the ledger's first ${String(lines)} lines`,
    bitcoinPending: (lines: number) =>
      `A proof of the first ${String(lines)} lines is waiting for its Bitcoin block (a few hours)`,
    bitcoinNone: "Recorded after the last timestamp: not timestamped yet",
    bitcoinMismatch: "The proof does not match this ledger or its block",
    bitcoinUnavailable: "The timestamp could not be read right now",
    step7: "Signed with ML-DSA-65",
    step7Note:
      "A post-quantum signature (FIPS 204) of a ledger head covering this record, checked in your browser with the published key.",
    signatureVerified: (date: string, lines: number) =>
      `Signed on ${date}, with the ledger's first ${String(lines)} lines`,
    signatureNone: "Recorded after the last signed head: not signed yet",
    signatureInvalid: "The signature does not verify for this ledger",
    signatureUnavailable: "The signatures could not be read right now",
    verified: "Verified: the record is exactly as it was sealed.",
    tampered: "Tampered: the content no longer matches its seal.",
    close: "Close",
  },
  externalHint: "(opens in a new tab)",
  mapUnavailable: "The map could not load in this browser.",
  mapSources: "Map sources",
  loading: "Loading the reach…",
  loadFailed: "The reach's records could not be loaded.",
  announceCase: "Case file:",
  announceBack: "Back to your cases.",
} as const;

/** How each level reads on a panel. */
export const LEVEL_LABELS = {
  validated: "Validated",
  estimated: "Estimated",
  indicative: "Indicative",
  // A reach with no station: the satellite's reading is the only one. The preregistered label
  // ("unvalidated: expected error from the transfer test") stays, word for word, beside it.
  unvalidated: "Satellite only",
  none: "No level",
} as const satisfies Record<Level, string>;

const dayMonth = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  timeZone: "UTC",
});
const dayMonthYear = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

/**
 * Formats an ISO date (`YYYY-MM-DD`) for the panels.
 *
 * @param isoDate - The date.
 * @param withYear - Also show the year.
 * @returns E.g. "14 Mar" or "14 Mar 2025".
 */
export function formatDate(isoDate: string, withYear = false): string {
  const date = new Date(`${isoDate}T00:00:00Z`);
  return (withYear ? dayMonthYear : dayMonth).format(date);
}

/**
 * Formats a number with an explicit sign (and a true minus sign).
 *
 * @param value - The number.
 * @param digits - Decimal places.
 * @returns E.g. "+0.11" or "−0.04".
 */
export function formatSigned(value: number, digits: number): string {
  const text = Math.abs(value).toFixed(digits);
  return value < 0 ? `−${text}` : `+${text}`;
}

/**
 * Formats a turbidity value for a panel: one decimal under 100, none above.
 *
 * @param value - The value.
 * @returns E.g. "30.5" or "124".
 */
export function formatValue(value: number): string {
  return value < 100 ? value.toFixed(1) : value.toFixed(0);
}

/**
 * Formats a temperature in °C with one decimal (and a true minus sign).
 *
 * @param value - The temperature.
 * @returns E.g. "18.9" or "−1.4".
 */
export function formatCelsius(value: number): string {
  return value.toFixed(1).replace("-", "−");
}

/**
 * Formats one of the gauge's readings: whole units from 100, one decimal from 10, two below.
 *
 * @param value - The reading.
 * @returns E.g. "1,240", "10.8" or "1.40".
 */
export function formatReading(value: number): string {
  const digits = Math.abs(value) >= 100 ? 0 : Math.abs(value) >= 10 ? 1 : 2;
  return value.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/**
 * A Landsat platform as people write it.
 *
 * @param platform - The record's platform, e.g. `landsat-9`.
 * @returns E.g. "Landsat 9".
 */
export function landsatName(platform: string): string {
  return platform.replace(/^landsat-/, "Landsat ");
}

/**
 * Whole days from one ISO date to another.
 *
 * @param from - Start date.
 * @param to - End date.
 * @returns `to - from` in days.
 */
export function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000);
}
