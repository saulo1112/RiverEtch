"""The ungauged reach's turbidity card (``docs/water-quality/preregistration-transfer.md``, §5).

The model is the transfer test's ``all`` fold: A4 trained the same way on the training-year pairs
of all nine river groups, with no site adjustment. The card holds what a record needs to use it
(the forest's file and hash, each feature's training range for abstention) and what the
preregistration fixes for an ungauged reach:

- **display:** a class in FNU (under 30, 30 to 100, 100 and over), never a value with a unit,
  and only if the pooled similar-river result reached _indicative_ (``transfer_pooled.json``);
  otherwise nothing, and the reach shows its relative NDTI only;
- **expected error:** the pooled similar-river result (MdSA, bias, class agreement), named with
  the SHA-256 of the file it comes from;
- **no level:** with no gauge, the reach is never scored and never earns a level of its own.

A reach **outside the tested region** (``docs/water-quality/preregistration-outside-us.md``) uses
the same model, ranges and class, with the basis ``outside_tested_region``, no expected error and
the label "Outside the tested region. No error estimate."

The cards are recomputed from committed files only, so ``quality transfer-verify`` checks them.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Final

from climate_pipeline.contract import observation_v2 as v2
from climate_pipeline.quality import cards
from climate_pipeline.quality import transfer_test as t
from climate_pipeline.quality.config import QualityConfig

CARDS = Path("docs/water-quality/ungauged")
REACH = "mississippi-st-joseph"
POOLED = t.RESULTS / "transfer_pooled.json"
LAB = Path("docs/water-quality/inputs/lab")  # a card's forest file is relative to it (reach run)
# Ungauged reaches outside the region the transfer test covered, and the file that fixed each.
OUTSIDE_REACHES: Final = {"firat-birecik": Path("docs/water-quality/preregistration-outside-us.md")}
REACHES: Final = (REACH, *OUTSIDE_REACHES)
OUTSIDE_LABEL: Final = "Outside the tested region. No error estimate."


def card(cfg: QualityConfig, root: Path, reach: str = REACH) -> dict[str, Any]:
    """The ungauged reach's turbidity card.

    Args:
        cfg: Settings.
        root: Repository root.
        reach: The reach's site id.

    Returns:
        The card (JSON-ready).
    """
    data = t.load(cfg, root)
    rows = data.training()  # every group's training years, in the exported table's order
    path = root / t.MODELS / t.ALL / t.MODEL_FILE
    fit = t.model(root, t.Fold(t.ALL, ()), [p.value for p in rows])
    names = list(fit.forest.feature_names)
    pooled = json.loads((root / POOLED).read_text(encoding="utf-8"))
    observed = [p.value for p in rows]
    decisive = {
        "parameters": {"kind": "lightgbm", "features": names,
                       "file": (t.MODELS / t.ALL / t.MODEL_FILE).relative_to(LAB).as_posix(),
                       "sha256": cards.file_sha256(path)},
        "adjustment": None,  # no site adjustment: nothing of the reach is known
        "featureRange": cards._range(rows, names),
        "targetRange": [round(min(observed), 6), round(max(observed), 6)],
        "display": "class" if pooled["ungauged_shows_class"] else "none",
        "classes": {"edgesFnu": list(v2.FNU_CLASS_EDGES), "labels": list(v2.FNU_CLASSES)},
    }  # fmt: skip
    digest = hashlib.sha256(json.dumps(decisive, sort_keys=True).encode()).hexdigest()
    outside = OUTSIDE_REACHES.get(reach)
    if outside is not None:
        return {
            "modelId": "A4:turbidity:core:transfer-all",
            "version": cards.VERSION, "target": "turbidity", "unit": "FNU", "window": "core",
            "candidate": "A4", "site": reach, "basis": v2.OUTSIDE, **decisive,
            "levels": [],  # no gauge: never scored, never a level of its own
            "label": OUTSIDE_LABEL,  # and no expected error: none was measured in this region
            "preregistration": outside.as_posix(),
            "preregistrationSha256": cards.file_sha256(root / outside),
            "training": ["2018-12-01", "2023-11-30"],
            "trainingPairs": {"usgs": len(rows), "groups": len({data.group(p) for p in rows})},
            "chosen": dict(fit.chosen),
            "parametersHash": digest,
        }  # fmt: skip
    return {
        "modelId": "A4:turbidity:core:transfer-all",
        "version": cards.VERSION, "target": "turbidity", "unit": "FNU", "window": "core",
        "candidate": "A4", "site": reach, "basis": v2.UNGAUGED, **decisive,
        "levels": [],  # no gauge: never scored, never a level of its own
        "expectedError": {
            "rule": pooled["similar_rule"],
            "sites": [s["site"] for s in pooled["similar_sites"]],
            "n": pooled["n"], "mdsa": pooled["mdsa"], "sspb": pooled["sspb"],
            "rho": pooled["rho"], "rhoLow": pooled["rho_low"],
            "classAgreement": pooled["class_agreement"],
            "coverage90Inside": pooled["coverage90_inside"],
            "source": POOLED.as_posix(), "sourceSha256": cards.file_sha256(root / POOLED),
        },
        "label": "unvalidated: expected error from the transfer test",
        "preregistration": t.PREREGISTRATION.as_posix(),
        "preregistrationSha256": cards.file_sha256(root / t.PREREGISTRATION),
        "training": ["2018-12-01", "2023-11-30"],
        "trainingPairs": {"usgs": len(rows), "groups": len({data.group(p) for p in rows})},
        "chosen": dict(fit.chosen),
        "parametersHash": digest,
    }  # fmt: skip


def card_text(c: dict[str, Any]) -> str:
    """A card as committed: indented JSON with sorted keys and a final newline."""
    return json.dumps(c, indent=2, sort_keys=True) + "\n"


def card_path(root: Path, reach: str = REACH) -> Path:
    """Where the card is committed."""
    return root / CARDS / reach / "turbidity.json"


def write(cfg: QualityConfig, root: Path, reach: str = REACH) -> Path:
    """Write the card (it is new; an existing one is never replaced by a different one).

    Args:
        cfg: Settings.
        root: Repository root.
        reach: The reach's site id.

    Returns:
        The card's path.

    Raises:
        FileExistsError: When a different card is already committed (cards are frozen).
    """
    path = card_path(root, reach)
    text = card_text(card(cfg, root, reach))
    if path.exists() and path.read_text(encoding="utf-8").replace("\r\n", "\n") != text:
        raise FileExistsError(f"{path} exists and differs: a card is never replaced")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def verify(cfg: QualityConfig, root: Path, reach: str = REACH) -> list[str]:
    """Recompute the card from the committed files and compare.

    Args:
        cfg: Settings.
        root: Repository root.
        reach: The reach's site id.

    Returns:
        The problems (empty when the committed card is the recomputed one).
    """
    path = card_path(root, reach)
    if not path.exists():
        return [f"{path.relative_to(root).as_posix()}: missing"]
    if path.read_text(encoding="utf-8").replace("\r\n", "\n") != card_text(card(cfg, root, reach)):
        return [f"{path.relative_to(root).as_posix()}: differs from its recomputation"]
    return []
