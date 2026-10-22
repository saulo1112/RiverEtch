# Preregistration: water temperature along the river, a reading spot that moves, and how a missing reading is shown (written 2026-10-22 UTC; decided after seeing the along-river turbidity records)

This file fixes, before any of it is read, how RiverEtch reads water temperature along the whole of
the two reaches that have a water-temperature card, how the app's reading spot moves along a reach,
and what the app shows where there is no reading. Its SHA-256 is a line of
`docs/ledgers/frozen-artifacts.jsonl`; nothing below runs before that line is anchored on Sepolia.

## 1. Why, and what is already known

- **Water temperature is read at one window.** Each of the two reaches with a water-temperature card
  reads it on its station's core window only, on Landsat's 30 m pixels: the Mississippi at Belle
  Chasse (its card checked at the USGS station at Baton Rouge: a mean error of 0.86 °C over 37
  locked-test passes) and the Platte at Louisville (1.28 °C over 24 passes)
  (`docs/water-quality/results/models/<site>/water_temperature.json`).
- **Turbidity is already read along the river** ([preregistration-along-river.md](preregistration-along-river.md)):
  one window every 600 m, a class per window and per pass, sealed in each reach's own ledger.
- **Decided after seeing results (disclosure).** The along-river turbidity records, the
  water-temperature records at the station windows and the cards' tests are known. No window along
  either reach has been read for water temperature.

## 2. Water temperature along the river, fixed here

- **Reaches:** the Mississippi at Belle Chasse and the Platte at Louisville, the two reaches with a
  water-temperature card. No other reach.
- **Windows:** the frozen plans of preregistration-along-river.md
  (`docs/water-quality/reach/<site>/along/windows.json`), unchanged: every placed window (38 at
  Belle Chasse, 35 on the Platte). Each window's core (its pixels at least 60 m from land, as for
  turbidity) is carried to Landsat's 30 m pixels exactly as the station's core is (a 30 m cell
  belongs to the window when its centre falls in the 20 m core).
- **Passes:** every Landsat 8/9 pass that has a water-temperature record of the reach (its station
  window had enough clear water), and every later one the daily run records. Each pass is read once:
  one read of the scene over a grid that holds every window.
- **The estimate, exactly as a record's:** the reach's frozen card, unchanged. On each window, the
  median surface temperature of its clear-water pixels (Landsat's QA_PIXEL water flag, not fill,
  not unusable), turned into water temperature by the card's line (`a + b × surface temperature`).
  A window has **no reading** when fewer than the card's minimum of water pixels are clear (10), or
  when its surface temperature lies outside the card's input range (where the card names one).
- **The class, never a value:** each estimate becomes one of six classes: under 10 °C, 10 to 15,
  15 to 20, 20 to 25, 25 to 30, and 30 °C and over. A value on an edge is in the upper class. The
  record keeps the class only. No station measures the water at these windows, so the error there
  has not been measured.
- **An along-river temperature record per pass** (`riveretch.along-temperature.v1`): the reach, the
  pass, the seal of its water-temperature record, the plan's SHA-256, the card and its hash, the
  STAC items, each window's class or the reason it has none, in the plan's order, and the code
  commit. It is sealed with the SHA-256 of its canonical JSON (keys sorted, no spaces, the seal left
  out) and chained in the reach's own ledger, `terrachain:<reach>:along-temperature`, which is
  anchored on Sepolia, timestamped on Bitcoin and signed like the others.

## 3. The reading spot, fixed here

- **It moves.** The app's reading spot can be moved to any placed window of the reach's plan: by
  dragging it, by clicking the river, or with the buttons that step upstream or downstream. It
  always snaps to the nearest window. "Back to the start" puts it back.
- **At the start** (the station's window, or the reading spot of a reach with no station), nothing
  changes: the app shows the sealed record's estimate, as before.
- **At any other window,** the app shows that window's class from the along-river records: turbidity
  on every reach, and water temperature on the two reaches of section 2. A value with a unit never
  appears there.
- **Its (?) says where the error comes from:** for turbidity on a US reach, "In 160 of 298 test
  passes on rivers the model never saw, the class matched the station"; at Birecik, "The model was
  tested on rivers in the United States; its error here has not been measured"; for water
  temperature, "The model was checked at a station; along the river its error has not been
  measured."
- **The station is marked on its own,** where it stands, on a reach that has one. It does not move
  with the reading spot.

## 4. A missing reading, fixed here

This section replaces, for the web app's display only, "or why it has none" in
[preregistration-along-river.md](preregistration-along-river.md), section 6, and "or the reason it
abstains" in [preregistration-outside-us.md](preregistration-outside-us.md), section 4.

- **Wherever a pass or a window has no estimate** (turbidity or water temperature; a record, an
  along-river record or an earlier year), the app says "No reading", and nothing more.
- **The charts draw no mark** for such a pass; its day stays on the time axis.
- **The reason is kept:** every sealed record still names it, unchanged, and the record's details in
  the app show it.

## 5. Runs, after the anchor

- After this file's line is anchored: `climate-pipeline reach along-temperature --site <reach>` for
  the two reaches, once over their 2026 water-temperature passes. The daily run then reads each new
  pass along the river. Every outcome is shown as it comes.
- No window, card, class edge or label changes after the anchor. A change is a new file with its own
  line and anchor.
