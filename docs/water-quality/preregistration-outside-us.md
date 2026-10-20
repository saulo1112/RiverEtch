# Preregistration: an ungauged reach outside the tested region, the Euphrates (Fırat) at Birecik, Türkiye (written 2026-10-20 UTC, before any reading of it)

This file fixes, before any scene of the reach is read, which reach is used, what its records may
show and how they are labelled. Its SHA-256 is a line of `docs/ledgers/frozen-artifacts.jsonl`,
whose head is anchored on Ethereum Sepolia (`terrachain:riveretch:frozen-artifacts`). The reach's
baseline and records run only after that anchor is mined. It is never edited: a change is a new
file with its own line and anchor.

Nothing here edits `preregistration-transfer.md`, its results, the St. Joseph card or any ledger
line.

## 1. Why, and what is already known

- `preregistration-transfer.md`, section 5, allows one ungauged reach: a **US** river reach. Every
  river the turbidity model was trained and tested on is in the United States, so its expected
  error (the pooled transfer test) was measured there only.
- The owner asked for a reach in Türkiye. This file is that change, made as a new file.
- **Outside the tested region, no error estimate exists.** The class may be right or wrong, and
  nothing here says how often. So the reach shows the class with the words **"Outside the tested
  region. No error estimate."** and no error figure of any kind.
- **Chosen after measuring widths (disclosure).** Section 2's points were measured before this file
  was written, with geometry only. No turbidity value, reflectance, index or record of any of these
  points was read, and none exists in the repository.

## 2. The reach, and how it was chosen

- **The model's widths:** the ungauged card abstains when a window's features fall outside their
  training range (`docs/water-quality/ungauged/mississippi-st-joseph/turbidity.json`,
  `featureRange`). Its channel width, `log_width_m`, spans 5.718999 to 6.649632: **304.6 to
  772.5 m**.
- **Widths measured** with the pilot's selection rule (the SCL water frequency of 2022–2025, the
  main channel at least 150 m wide), the rule St. Joseph's window was chosen by:

  | Point                                   | Latitude, longitude | Point from                                              | Main channel                   |
  | --------------------------------------- | ------------------- | ------------------------------------------------------- | ------------------------------ |
  | Fırat (Euphrates) at the Birecik Bridge | 37.02655, 37.97299  | OSM way 13638374, the bridge                            | 322.5 m                        |
  | Fırat below the Birecik Dam             | 37.045, 37.915      | approximate (snapped 220 m)                             | 320.0 m                        |
  | Dicle (Tigris) at Cizre                 | 37.32731, 42.19697  | OSM way 93835200                                        | 304.6 m                        |
  | Seyhan at Adana                         | 36.98546, 35.33489  | OSM way 82082850                                        | 240.0 m                        |
  | Meriç (Evros) at Edirne                 | 41.66341, 26.55212  | Nominatim, the Meriç road bridge                        | 200.0 m                        |
  | Dicle below Cizre                       | 37.27, 42.25        | approximate (snapped 465 m)                             | 200.0 m                        |
  | Kızılırmak near Bafra                   | 41.58527, 35.89278  | OSM way 1172193650                                      | 80 m (water mask), under 150 m |
  | Ceyhan at Ceyhan                        | 37.02812, 35.81006  | OSM way 36093036                                        | 80 m (water mask), under 150 m |
  | Yeşilırmak at Çarşamba                  | 41.20641, 36.72235  | Nominatim, a quarter named Yeşilırmak (snapped 1.39 km) | 89 m (water mask), under 150 m |
  | Meriç near Enez                         | 40.745, 26.06       | approximate                                             | 89 m (water mask), under 150 m |
  | Kızılırmak delta                        | 41.63198, 35.91241  | OSM way 1172193650                                      | no main channel within 1.5 km  |
  | Meriç at İpsala, Dicle on the border    | approximate         | approximate                                             | no channel found within 1.5 km |

- **The rule (set after these widths were known):** the point whose width lies inside the model's
  range by the largest margin from either edge, in log width. The Fırat at the Birecik Bridge
  (322.5 m) is inside by 0.057; the Dicle at Cizre (304.6 m) sits on the lower edge (margin 0), and
  the Cizre Dam has been under construction just upstream of it since September 2024. **Chosen: the
  Fırat at Birecik.**
- **The reach:** the Fırat from about 2 km below the Birecik Dam (37.045, 37.915, snapped to the
  water by the run) down to the Birecik Bridge (37.02655, 37.97299), about 5.5 km apart in a
  straight line: river water, 320 to 322.5 m wide at both ends. Its site file,
  `pipeline/reaches/firat-birecik.yaml`, is frozen with this file. The class is read on the window
  at the Birecik Bridge, the point measured above.
- **Dams (disclosure):** the Birecik Dam lies 8 km upstream of Birecik town and the Atatürk Dam 60
  km upstream of it; the Karkamış Dam downstream is a run-of-river plant with a lake behind it
  (Wikipedia, "Birecik Dam" and "Karkamış Dam"; IEA Hydro, Annex VIII case study). Reservoirs
  upstream may hold back much of the river's sediment **[not measured]**, so the water may be
  clearer than on the rivers the model learned from. Then the records may show "under 30" on most
  passes, or abstain because a feature lies outside its training range. Either outcome is shown as
  it comes.
- **No actor is the subject.** The reach is chosen for its width. No dam, operator, licence or
  permit is the subject of any record.

## 3. The model

- The ungauged card's model, unchanged: A4 trained on the training-year pairs of all nine US river
  groups (the transfer test's `all` fold), its forest file and hash, its feature ranges and its
  class edges. A card of its own (`docs/water-quality/ungauged/firat-birecik/turbidity.json`) names
  them, with the basis `outside_tested_region`, the label below and **no expected error**. That
  card is frozen with this file.
- The window's guards and abstention rules are the reach runs', unchanged: "What a record says" in
  `docs/water-quality/reach/README.md`.

## 4. What a record may show, fixed here

- **A class** (under 30, 30 to 100, 100 FNU and over), never a value with a unit; or the reason it
  abstains.
- The label **"Outside the tested region. No error estimate."**, wherever the class appears.
- **No error figure:** not the transfer test's, not any other.
- The reach's relative indices (NDTI and NIR/red per sub-reach, against its own frozen baseline),
  as every reach shows.
- **No level, never scored:** with no gauge, nothing can score a record, and the reach never earns a
  level.
- No station flow or level: no public station of this river is used.

## 5. Runs, after the anchor

- **Settings** (added to `pipeline/reach.yaml` only after the anchor, so no run reads the reach
  before it): `site: firat-birecik`, `station_source: ungauged`, `estimate_point` the Birecik
  Bridge, `targets: [turbidity]`, the card of section 3, `timezone: Europe/Istanbul`,
  `rainy_months: [11, 12, 1, 2, 3, 4]`, `geometry_start: 2022-01-01`, `geometry_end: 2025-12-31`,
  `baseline_start: 2019-01-01`, `baseline_end: 2025-12-31`, `baseline_max_gb: 6.0`.
- **Baseline** (`reach baseline`): the reach's usable Sentinel-2 L2A scenes from 2019-01-01 to
  2025-12-31 (6 GB cap, as the other reaches), geometry from 2022-2025. Its time zone is
  Europe/Istanbul; its rainy months are November to April, the months with at least 30 mm on
  average (WMO climate normals 1991–2020 for Birecik, via NOAA).
- **Records** (`reach run`): every usable pass from 2026-01-01 to the run, then the daily runs. Each
  record is sealed, listed in the reach's ledger and anchored as the other reaches' are.
- Every record is kept, an abstention included.

## Sources

- Wikipedia, "Birecik Dam": https://en.wikipedia.org/wiki/Birecik_Dam
- Wikipedia, "Karkamış Dam": https://en.wikipedia.org/wiki/Karkam%C4%B1%C5%9F_Dam
- Wikipedia, "Cizre Dam": https://en.wikipedia.org/wiki/Cizre_Dam
- IEA Hydropower, Annex VIII case study (the border Euphrates):
  https://www.ieahydro.org/media/a92cd91b/Annex_VIII_CaseStudy1003_BorderEuphrates_Turkey.pdf
- Wikipedia, "Birecik" (climate table: NOAA, WMO climate normals 1991–2020):
  https://en.wikipedia.org/wiki/Birecik
- OpenStreetMap ways 13638374 (Birecik Köprüsü), 28048509 (Birecik Barajı), 128497237 (Karkamış
  Barajı), 93835200, 82082850, 1172193650, 36093036.
