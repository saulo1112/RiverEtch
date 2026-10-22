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
  // A pass or a stretch with no estimate, wherever it appears (preregistration-along-temperature.md,
  // section 4): the reason stays in the record, shown in its details.
  noReading: "No reading",
  noValue: "No reading",
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
    // A tile's foot, short enough for one line; the whole sentence opens from its (?).
    tileShortMedian: (mdsa: string) => `Typical error ${mdsa} %`,
    tileShortMean: (mae: string) => `Average error ${mae} °C`,
    tileHelpLabel: "About this error",
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
    "A turbidity class read from the satellite. The model was tested on rivers in the United States; its error here has not been measured.",
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
    // The cards' own labels, as preregistration-transfer.md and preregistration-outside-us.md fixed
    // them (a test compares them with the frozen cards). Since preregistration-along-river.md,
    // section 6, the app shows the class alone and these facts behind its (?).
    label: "Unvalidated: expected error from the transfer test",
    outsideLabel: "Outside the tested region. No error estimate.",
    noClass: "No reading",
    errorTitle: "How far off it tends to be, on rivers it never saw",
    agreement: (k: number, n: number) =>
      `In ${String(k)} of ${String(n)} test passes on rivers it never saw, the class matched the station.`,
    agreementShort: (k: number, n: number) => `Class right in ${String(k)} of ${String(n)} tests`,
    median: (mdsa: string, sites: number) =>
      `Half of those estimates were off by less than ${mdsa} % of the station's value (${String(sites)} sediment-carrying rivers like this one).`,
    baselineNote:
      "With no station here there is no usual value to compare with; each river's comparison is in How it works, under Does it work?",
    trainedOn:
      "The model never saw this reach. It did learn from two other Mississippi stations, at Cape Girardeau (upstream) and Belle Chasse (downstream).",
    window: "Reading spot (no station)",
    legendWindow: "The reading spot",
    mapCaption: "Reading spot",
    // Why a reach with no station may have no Climate tab.
    noClimate:
      "No open daily flow record of this river was found, so this case has no Climate tab.",
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
      "One clear Sentinel-2 pass: the turbidity at the station spot, in FNU, with the range the station's value should fall in 9 times out of 10. The arrows under it, or the orange spot dragged on the map, read any other stretch of the river, as a class.",
    summaryUngauged:
      "One clear Sentinel-2 pass: the water's turbidity class at the reading spot, in FNU. The (?) beside it says how often such a class was right. The arrows under it, or the orange spot dragged on the map, read any stretch of the river.",
    summaryOutside:
      "One clear Sentinel-2 pass: the water's turbidity class at the reading spot, in FNU. The (?) beside it says how the model was tested. The arrows under it, or the orange spot dragged on the map, read any stretch of the river.",
    trustTitle: "What it is worth, and what protects it",
    trust:
      "The level says how far the model was tested; the (?) explains it. Fingerprinted: the reading's SHA-256 is fixed. Posted on Ethereum: its line of the record list is stored on a public chain.",
    verifyTitle: "Check it yourself",
    verify:
      "Check this reading: your browser recomputes its fingerprint, walks the record list and the model sheet, then reads Ethereum (test network), the Bitcoin timestamp and the quantum-safe signature. No wallet needed.",
    proofTitle: "Take it out, check it later",
    proof:
      "Export with proof downloads the readings with what proves they have not changed since they were fixed. Check a file tells you whether a file someone sent you still matches the record. Nothing is uploaded.",
    layersTitle: "The map is relative",
    layers:
      "NDTI per pixel, compared with this reach's own passes. It has no unit and is not validated: only the amber spot carries a value or a class.",
    tabsTitle: "The year, pass by pass",
    tabs: "The tabs hold the year's passes beside the station, the station's own readings and climate record, and the track record of readings sealed before the station's value was read.",
    tabsUngauged:
      "The tabs hold the year's passes by class, the turbidity index against the river's own past, the image in detail and, where a station upstream measures it, the river's flow. With no station there is no track record: nothing here is scored.",
    alongTitle: "Along the whole river",
    along:
      "Each column is a pass and each row 600 m of river, coloured by its class. Move over a stretch to find it on the map; click a cell to open that pass and move the reading spot there.",
    endTitle: "That is the record",
    end: "Sealing proves a number was not changed; it does not prove it was right. The tests show how often it was right.",
  },
  trust: {
    label: "Record status",
    sealed: "Fingerprinted",
    anchored: (date: string) => `Posted on Ethereum ${date}`,
    checking: "Checking Ethereum…",
    pending: "Waiting for the next post on Ethereum",
    mismatch: "No longer matches its post on Ethereum",
    unavailable: "Ethereum not readable right now",
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
    title: "Proof",
    details: "Record details",
    ofPass: "Sentinel-2 pass",
    ofThermal: "water temperature",
    scene: "Scene",
    images: "Sentinel-2 images",
    landsatImages: "Landsat images",
    processing: "Processing",
    thermalProcessing: "Collection 2 Level-2 · band 10 surface temperature",
    window: "Station spot",
    // A pass with no estimate: the reason its record names (the panels say "No reading" only).
    noReadingWhy: "Why no reading",
    waterPixels: "water pixels",
    code: "Code",
    card: "Model sheet",
    seal: "Fingerprint (SHA-256)",
    replaces: "Replaces",
    replacesNote: "read again with four classes; still in the record list",
    verify: "Check this reading",
    verifying: "Checking…",
    download: "Download the record (JSON)",
    sealed: "Its content matches its fingerprint (SHA-256)",
    broken: "Its content no longer matches its fingerprint",
    inLedger: "Listed in the reach's record list",
    notInLedger: "Not found in the record list",
    chain: "Record list unbroken",
    chainBroken: "Record list broken",
    lines: "lines",
    cardOk: "The model sheet (what the model was) matches the one the record names",
    cardBad: "The model sheet (what the model was) does not match the one the record names",
    notAnchored:
      "Not posted on a public chain yet: the fingerprint and the record list are checked here.",
    anchoredHint:
      "Each record list's last line is posted on Ethereum (test network) as a public timestamp.",
    contract: "The contract on Ethereum",
    chainAnchored: (date: string, block: number) =>
      `Posted on Ethereum (test network) on ${date} (block ${String(block)})`,
    chainPending: "Waiting for the next post on Ethereum (test network)",
    chainMismatch: "The record list no longer matches its post on Ethereum (test network)",
    chainUnavailable: "Not checked against Ethereum (offline)",
    viaWallet: "Read through your own wallet's connection to Ethereum (test network)",
    viaPublic:
      "Read through a public node of Ethereum (test network); connect a wallet to read it through your own",
    anchorAction: "Post this reach's record lists on Ethereum (test network)",
    anchoring: "Waiting for the wallet and the block…",
    anchoredTx: (ledgers: number) =>
      `${String(ledgers)} ${ledgers === 1 ? "record list" : "record lists"} posted · view the transaction`,
    upToDate: "The record lists are already posted up to their last line.",
    anchorFailed: "The post failed or was rejected in the wallet.",
    failed: "The reading could not be checked.",
    // Where the three boards are listed.
    boards: "If one board disappears, the other two still hold the record.",
  },
  // The Proof panel's two actions (Export with proof, Check a file) and a whole file's report.
  proof: {
    whyLabel: "What does this prove?",
    why: "Every reading has a fingerprint (SHA-256), posted on Ethereum (test network), timestamped on Bitcoin and signed with a quantum-safe signature. Any later change to a reading would show. A fingerprint proves a reading has not changed since it was fixed; it does not prove the reading is right.",
    export: "Export with proof",
    exportPurpose: "Take your data out with the proof that it has not changed since it was fixed.",
    check: "Check a file",
    checkPurpose: "Got a RiverEtch file from someone? See if it matches the record.",
    checking: "Checking the file…",
    accepts:
      "An export (.zip), a table (CSV) or one record (JSON). Checked in your browser; nothing is uploaded.",
    unreadable: "This is not a RiverEtch file.",
    failed: "The file could not be read.",
    rows: (n: number) => `${String(n)} ${n === 1 ? "row" : "rows"} checked`,
    ethereum: (n: number) => `${String(n)} unchanged and posted on Ethereum`,
    bitcoin: (n: number) => `${String(n)} unchanged and on Bitcoin`,
    waiting: (n: number) => `${String(n)} unchanged, waiting for the next post`,
    offline: "not checked against Ethereum (offline)",
    changed: (n: number) => `${String(n)} changed`,
    notFound: (n: number) => `${String(n)} not found`,
    missing: (n: number) => `${String(n)} missing`,
    signed: (n: number) =>
      `${String(n)} unchanged and under the quantum-safe signature (ML-DSA-65).`,
    changedTitle: "What changed",
    notFoundTitle: "Not found on RiverEtch",
    missingTitle: "Missing from the file",
    row: (row: number, date: string) => `Row ${String(row)}${date === "" ? "" : ` (${date})`}`,
    missingRow: (date: string, reach: string) => `${date} · ${reach}`,
    change: (column: string, sealed: string, given: string) =>
      `${column}: fixed as ${sealed === "" ? "(empty)" : sealed}, in the file ${given === "" ? "(empty)" : given}`,
    whole: "the whole record",
    more: (n: number) => `and ${String(n)} more`,
    manifest: (sha: string) =>
      `This export's manifest fingerprint is ${sha}. It should be the one in the citation line of its READ-ME.`,
  },
  // The "Export with proof" dialog.
  exportDialog: {
    title: "Export with proof",
    river: "River",
    thisRiver: (title: string) => `This river: ${title}`,
    allRivers: "All rivers",
    data: "Data",
    datasets: {
      turbidity: "Turbidity",
      temperature: "Water temperature",
      along: "Turbidity along the river",
      alongTemperature: "Temperature along the river",
    },
    shape: "Reach shape (GeoJSON)",
    period: "Period",
    all: "All",
    range: "Between two dates",
    from: "From",
    to: "To",
    periodNote: "Sealed records start in 2026.",
    counting: "Counting the readings…",
    summary: (readings: number, ethereum: number, bitcoin: number, waiting: number) =>
      `${String(readings)} readings · ${String(ethereum)} on Ethereum · ${String(bitcoin)} on Bitcoin · ${String(waiting)} waiting for the next post`,
    summaryOffline: (readings: number, bitcoin: number) =>
      `${String(readings)} readings · Ethereum not read right now (offline) · ${String(bitcoin)} on Bitcoin`,
    none: "No sealed readings in this choice.",
    download: "Download the .zip",
    building: "Building the zip…",
    saved: (name: string, sha: string) =>
      `Saved ${name}. Its manifest fingerprint: ${sha.slice(0, 16)}…`,
    failed: "The export could not be built. Try again.",
    local: "Built in your browser; nothing is uploaded.",
    close: "Close",
  },
  legendTitle: "NDTI per pixel (relative)",
  // The Turbidity layer: each stretch of river coloured by its class on the pass.
  legendClass: "Turbidity along the river",
  legendClassNone: "No reading on this stretch",
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
  timelineNoValue: "No reading",
  timelineHint: "Select a pass to see its map and record.",
  tools: {
    label: "Map tools",
    layer: "What the river shows",
    classes: "Turbidity",
    ndti: "NDTI",
    photo: "True color",
    none: "Off",
    opacity: "Layer opacity",
    layers: "Layers",
    overlays: "Overlays",
    outline: "River corridor",
    outlineNote: "The stretch of river the satellite reads",
    window: "Station spot",
    windowNote: "Where the number is read, at the station, so the two can be compared",
    windowUngauged: "Reading spot",
    windowUngaugedNote: "Where the turbidity class is read",
    terrain: "3D terrain",
    terrainNote: "The land in relief",
    compare: "Compare",
    compareWith: "Compare the selected pass with the one on…",
    compareStop: "Stop comparing",
    compareHint:
      "Drag the split on the map to sweep between the two passes. Click Compare again to stop.",
    export: "Export with proof",
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
    noClass: "No reading",
    km: "km",
    of: "of",
  },
  tabs: {
    quality: "Water quality",
    series: "Turbidity",
    thermal: "Water temperature",
    climate: "Climate",
    pass: "Image details",
    scoreboard: "Track record",
    along: "Along the river",
  },
  // The earlier years, 2019 to 2025 (preregistration-archive.md): recomputed, not sealed.
  archive: {
    label: "Recomputed, not sealed",
    phases: {
      training: "training years: the model learned from this period",
      test: "locked test: passes the model never saw",
      after: "after the locked test",
      unseen: "a river the model never saw",
    },
    helpLabel: "About earlier years",
    help: "Read again in 2026 from the public satellite images, with the same frozen models as the sealed records. A pass read after the fact is not a record, so nothing here is sealed or anchored. Training years: the model learned from this period, so its passes do not test it. Locked test: passes the model never saw while it was built.",
    year: "Year",
    yearLabel: "Which year the case shows",
    earlier: "Earlier year",
    later: "Later year",
    sealedYear: "Sealed records",
    loading: (year: string) => `Loading ${year}…`,
    back: (year: string) => `Back to ${year}`,
    recordCaption: (year: string) => `${year} · recomputed, not sealed`,
    recordText:
      "Earlier years are read again from the public images with the same frozen models. They are not sealed records, so there is nothing to verify here. The year's file names the code and the models, so anyone can read the same passes again and compare.",
    download: (year: string) => `Download ${year} (JSON)`,
    mapNote:
      "An earlier year: each stretch's class, painted on the river's 2026 outline. No image of the pass is kept.",
    quality: "Recomputed from the satellite, not sealed",
  },
  // Along the whole river (preregistration-along-river.md): a class for each stretch, pass by pass.
  along: {
    noReading: "No reading",
    hint: "Each column a pass, each row 600 m of river from upstream to downstream",
    empty: "The turbidity along the river is not available for this reach yet.",
    emptyTemperature: "The water temperature along the river is not available for this reach yet.",
    chartLabel:
      "Turbidity class along the river, pass by pass. Left and right change the pass; up and down move the reading spot along the river.",
    chartLabelTemperature:
      "Water temperature class along the river, Landsat pass by pass. Left and right change the pass; up and down move the reading spot along the river.",
    // What the tab shows, where the reach has both (preregistration-along-temperature.md).
    variable: { label: "What the chart shows", turbidity: "Turbidity", temperature: "Temperature" },
    stretch: (from: string, to: string) => `km ${from} to ${to}`,
    read: (k: number, n: number) => `${String(k)} of ${String(n)} stretches read on this pass`,
    unit: "km from upstream",
    unitShort: "km",
    // The caption's swatches, short enough for a phone ("FNU" closes the list).
    short: {
      under_30: "Under 30",
      "30_to_50": "30–50",
      "50_to_100": "50–100",
      "100_and_over": "100+ FNU",
    } as Readonly<Record<string, string>>,
    // The temperature caption's swatches ("°C" closes the list).
    shortTemperature: {
      under_10: "Under 10",
      "10_to_15": "10–15",
      "15_to_20": "15–20",
      "20_to_25": "20–25",
      "25_to_30": "25–30",
      "30_and_over": "30+ °C",
    } as Readonly<Record<string, string>>,
    station: "Station",
    spot: "Reading spot",
  },
  // The water-temperature classes along the river (preregistration-along-temperature.md).
  temperatureClasses: {
    under_10: "Under 10 °C",
    "10_to_15": "10 to 15 °C",
    "15_to_20": "15 to 20 °C",
    "20_to_25": "20 to 25 °C",
    "25_to_30": "25 to 30 °C",
    "30_and_over": "30 °C and over",
  } as Readonly<Record<string, string>>,
  // The reading spot that moves (preregistration-along-temperature.md, section 3).
  spot: {
    label: "Reading spot",
    stretch: (from: string, to: string) => `km ${from} to ${to}`,
    atStation: "at the station",
    atStart: "where the daily record is read",
    upstream: "Move the reading spot upstream",
    downstream: "Move the reading spot downstream",
    back: "Back to the start",
    helpLabel: "About the reading spot",
    help: "Drag the orange spot along the river, click the river, or use these arrows. It snaps to the nearest 600 m stretch. Away from the start, each stretch shows a class from the along-river records, never a value.",
    turbidity: "Turbidity class",
    temperature: "Water temperature class",
    // Behind the class's (?), word for word as section 3 fixes them.
    usHelp: (k: number, n: number) =>
      `In ${String(k)} of ${String(n)} test passes on rivers the model never saw, the class matched the station.`,
    outsideHelp:
      "The model was tested on rivers in the United States; its error here has not been measured.",
    temperatureHelp:
      "The model was checked at a station; along the river its error has not been measured.",
    classHelpLabel: "About this class",
    chartKey: (stretch: string) =>
      `Each pass's turbidity class at ${stretch} (the height means the class only)`,
    temperatureKey: (stretch: string) =>
      `Each Landsat pass's water temperature class at ${stretch} (the height means the class only)`,
    noReadings: "No reading on this stretch this year.",
    // The map: the station, marked on its own where it stands.
    station: (id: string) => `USGS station ${id}`,
    legendSpot: "The reading spot (drag it along the river)",
    legendStation: "The USGS station",
    // The record of a stretch: the pass's along-river record.
    recordCaption: (date: string) => `Along the river · Sentinel-2 pass · ${date}`,
    recordTemperatureCaption: (platform: string, date: string) =>
      `Along the river · ${platform} · ${date}`,
    recordStretch: "Stretch",
    // "Go to coordinates": one click on the orange spot, or its button in the case file.
    coordsOpen: "Enter coordinates",
    coordsTitle: "Go to coordinates",
    coordsSystem:
      "WGS 84 (EPSG:4326), decimal degrees: the system GPS uses and Google Maps shows. Latitude first.",
    coordsLat: "Latitude",
    coordsLon: "Longitude",
    coordsGo: "Go",
    coordsClose: "Close coordinates",
    coordsNow: (point: string) => `This stretch's centre: ${point}`,
    coordsNote:
      "The spot moves to the nearest 600 m stretch: a reading covers its window, 300 m around its centre, not the exact point.",
    coordsMoved: (stretch: string, m: number) =>
      `Moved to ${stretch}. Its centre is ${String(m)} m from your point.`,
    coordsTooFar: (km: string) =>
      `That point is ${km} km from this reach's river, so the spot did not move.`,
    coordsInvalid:
      "Type a latitude from −90 to 90 and a longitude from −180 to 180, such as 29.85512 and −89.99731.",
    recordWindow: (id: string, stretch: string) => `${id} · ${stretch}`,
  },
  rivers: {
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
    noneYet: "none yet",
    // A scored station value's approval, in a word (its help says what it means).
    approvedWord: "approved",
    provisionalWord: "may be revised",
    turbidity: "Turbidity",
    temperature: "Water temperature",
    results: {
      inside: "Inside the range",
      outside: "Outside the range",
      pending: "No station value yet",
      none: "No station value",
      abstained: "No reading",
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
    // A reach with no station: the flow measured at a station on the same river (reach.yaml,
    // climate_station), said where it is.
    noteContext: (name: string) =>
      `Below, the river's daily flow measured upstream (${name}): this reach has no station of its own. Measurements, not a trend or an attribution.`,
    contextHelpLabel: "About this station",
    // A reach with no open station record of its river: the GloFAS flood model's flow (reach.yaml,
    // climate_model), named as modelled and credited as the data's licence asks (CC BY 4.0).
    model: {
      before: "Below, the river's daily flow from the GloFAS flood model (data by ",
      link: "Open-Meteo.com",
      url: "https://open-meteo.com/",
      after:
        "), as no open station record was found: modelled, not measured, and not a trend or an attribution.",
      helpLabel: "About this model",
    },
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
    chartModel: (measure: string, model: string) => `${measure} per year in the ${model}`,
    table: "Every year of the station's record",
    tableModel: "Every year of the modelled record",
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
    none: "No value at this pass",
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
  play: {
    play: (year: string) => `Play ${year}`,
    pause: "Pause",
    previous: "Previous pass",
    next: "Next pass",
  },
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
  // The day chooser (beside the case file's date, and in Compare): the year's passes by month.
  calendar: {
    choose: (date: string) => `Shown: ${date}. Choose another day`,
    label: "Choose a day the satellite passed",
    previous: "Previous month",
    next: "Next month",
    weekdays: [
      ["Mo", "Monday"],
      ["Tu", "Tuesday"],
      ["We", "Wednesday"],
      ["Th", "Thursday"],
      ["Fr", "Friday"],
      ["Sa", "Saturday"],
      ["Su", "Sunday"],
    ] as const,
    noReading: "no reading",
    passes: (n: number) => `${String(n)} passes`,
    passesOn: (n: number, date: string) =>
      `${n === 2 ? "Two" : String(n)} satellites passed on ${date}`,
    keyRead: "A reading",
    keyNone: "No reading",
    keyEmpty: "Grey: no pass",
  },
  verify: {
    title: "Checking the reading",
    showSteps: "Show the steps",
    // The verdict first, in one sentence: unchanged since when, and on which boards.
    same: (date: string) => `Same as when it was fixed on ${date}.`,
    boardsBoth: "On Ethereum and on Bitcoin.",
    boardsEthereum: "On Ethereum; waiting for its Bitcoin block.",
    boardsPending: "Waiting for the next post on Ethereum.",
    boardsOffline: "Not checked against Ethereum (offline).",
    boardsMismatch: "Its record list no longer matches its post on Ethereum.",
    changed: "Changed since it was fixed: its fingerprint no longer matches.",
    step1: "Canonical content",
    step1Note: "Keys sorted, no spaces, numbers as written; the fingerprint itself left out.",
    step2: "SHA-256 of the content",
    stated: "Fixed",
    computed: "Recomputed",
    step3: "Place in the record list",
    step3Note:
      "Each line names the SHA-256 of the line before: changing one breaks every link after it.",
    step4: "Model sheet (what the model was)",
    step5: "Posted on Ethereum (test network)",
    step5Note:
      "The SHA-256 of a line of the record list, stored on Ethereum at a block's time, commits to every line above it.",
    step6: "Timestamped on Bitcoin",
    step6Note:
      "An OpenTimestamps proof that a last line covering this reading existed by a Bitcoin block, checked against two public block explorers. It needs no key: only hashes.",
    bitcoinConfirmed: (date: string, height: number, lines: number) =>
      `In Bitcoin block ${String(height)} (${date}), with the record list's first ${String(lines)} lines`,
    bitcoinPending: (lines: number) =>
      `A proof of the first ${String(lines)} lines is waiting for its Bitcoin block (a few hours)`,
    bitcoinNone: "Fixed after the last timestamp: not timestamped yet",
    bitcoinMismatch: "The proof does not match this record list or its block",
    bitcoinUnavailable: "The timestamp could not be read right now",
    step7: "Quantum-safe signature (ML-DSA-65)",
    step7Note:
      "A signature future quantum computers cannot forge (FIPS 204), of a last line covering this reading, checked in your browser with the published key.",
    signatureVerified: (date: string, lines: number) =>
      `Signed on ${date}, with the record list's first ${String(lines)} lines`,
    signatureNone: "Fixed after the last signed line: not signed yet",
    signatureInvalid: "The signature does not verify for this record list",
    signatureUnavailable: "The signatures could not be read right now",
    verified: "Unchanged: the reading is exactly as it was fixed.",
    tampered: "Changed: the content no longer matches its fingerprint.",
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
