# Preregistration: the earlier years' images, 2019 to 2025, on the map (written 2026-10-22 UTC; decided after seeing the earlier years' classes)

This file fixes, before any of them is drawn, which images of the earlier years' passes RiverEtch
draws, how, and how the app shows them. Its SHA-256 is a line of
`docs/ledgers/frozen-artifacts.jsonl`; nothing below runs before that line is anchored on Sepolia.

## 1. Why, and what is already known

- **No image of an earlier pass is kept.** The earlier years were read once
  ([preregistration-archive.md](preregistration-archive.md)): each pass's class on every window
  along the river and the estimate at the start, written to
  `docs/water-quality/reach/<site>/examples/archive/<year>.json` (commit `0a7c2dd`). Its section 4
  fixes that the map paints an earlier year's classes on the water outline of a 2026 pass, with no
  per-pixel index and no true-colour image, because none was drawn.
- **What that hides.** A reader cannot see the river as the satellite saw it that day, and a class
  painted on a 2026 outline does not show where that pass's own clouds, glint or missing data were.
- **Decided after seeing results (disclosure).** The earlier years' files above, their classes and
  their estimates are known.

## 2. What is drawn, fixed here

- **Which passes:** every pass listed in a reach's `archive/<year>.json`, for the four reaches the
  app shows (`mississippi-belle-chasse`, `platte-louisville`, `mississippi-st-joseph` and
  `firat-birecik`) and the years 2019 to 2025. No other pass, and none of them is left out by any
  other rule.
- **What, and how:** the same two images a 2026 record's pass has, drawn by the same code as
  `climate-pipeline reach render` (`scene_map` and `true_color`, `pipeline/src/climate_pipeline/reach/render.py`):
  - the NDTI map on the corridor's 10 m grid, under the screening's pixel guards (scene
    classification, the red + green floor, the B11 glint limit), with the encoding of the reach's
    `maps.json` (NDTI, place along the reach, part of the corridor, usable or not);
  - the true-colour image (B04, B03, B02) over the same box, with the same gain, gamma and WebP
    quality.
- **The same frame** as the reach's 2026 maps: the corridor's box, its size and its corners, so an
  earlier image lies exactly where a 2026 one does.
- **Nothing is read or estimated.** No value, class, phase or label of the earlier years changes,
  and their files are not changed. The images are a view of the pass, not a measurement.

## 3. What is written, fixed here

- Per reach and per year, `docs/water-quality/reach/<site>/examples/archive-maps/<year>.json`
  (each image's pass, date and files, the code commit, the grid's size and corners) and the images
  under `archive-maps/<year>/`. Nothing is sealed or anchored.
- **Published on the `data` branch only,** by a manual workflow after the anchor; the images are
  not committed to `main` and are not part of the web build. A pass whose images fail to draw is
  retried by the next run; a pass the catalogue no longer lists is named as missing, and nothing
  drawn is changed afterwards.

## 4. How the app shows them, fixed here

- **A pass with its own images** shows them as a 2026 pass does: the NDTI layer (relative, no unit,
  on the same colour ramp as the reach's 2026 maps), the true-colour layer, and the turbidity
  layer, which paints each stretch's class on that pass's own water and hatches the pixels that
  pass left unusable. This replaces, for that pass, the map sentence of
  preregistration-archive.md, section 4.
- **A pass without its own images** is shown as preregistration-archive.md, section 4, fixes: its
  classes on a 2026 pass's water outline, and the legend says so.
- **Compare** shows two passes the same way, whichever their years.
- **Everything else stays** as preregistration-archive.md fixes it: "Recomputed, not sealed"
  wherever an earlier year appears, each pass's phase, and nothing to check.

## 5. Runs, after the anchor

- After this file's line is anchored: `climate-pipeline reach archive-maps` for the four reaches
  and each year, once, in the manual workflow "Earlier years' images", which publishes them to the
  `data` branch. Every outcome is shown as it comes.
- No pass, image, rule or label changes after the anchor. A change is a new file with its own line
  and anchor.
