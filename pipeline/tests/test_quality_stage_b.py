import hashlib
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from climate_pipeline.quality import stage_b
from climate_pipeline.screening.stac import Acquisition


def test_an_early_scene_takes_its_datatake_from_the_l2a_item() -> None:
    scene = SimpleNamespace(item_id="S2A_MSIL2A_20160906T152642_R025_T18PXQ_20210212T081845",
                            mgrs_tile="18PXQ", bbox=(-74.0, 6.0, -73.0, 7.0))  # fmt: skip
    other = SimpleNamespace(item_id="S2A_MSIL2A_20160906T152642_R025_T18PXR_20210212T081845",
                            mgrs_tile="18PXR", bbox=(-74.0, 7.5, -73.0, 8.5))  # fmt: skip
    acq = cast(Acquisition, SimpleNamespace(scenes=(other, scene)))
    box = (-73.6, 6.4, -73.5, 6.5)
    assert stage_b.l2a_datatake(acq, box) == ("S2A_MSIL1C_20160906T152642", "18PXQ")
    assert stage_b.l2a_datatake(acq, (-80.0, 0.0, -79.0, 1.0)) == ("", "")


def test_tss_scenes_come_first_then_by_day() -> None:
    entries = {("a", "k1"): {"targets": {"turbidity"}, "day": date(2020, 1, 1)},
               ("b", "k2"): {"targets": {"tss", "turbidity"}, "day": date(2024, 1, 1)},
               ("c", "k3"): {"targets": {"tss"}, "day": date(2021, 1, 1)}}  # fmt: skip
    order = sorted(entries, key=lambda k: stage_b.priority(entries[k], k[0]))
    assert order == [("c", "k3"), ("b", "k2"), ("a", "k1")]


def test_route_b_keys_and_the_summary(tmp_path: Path) -> None:
    path = tmp_path / "windows.csv"
    path.write_text("station,key,window\ns1,k1,300m\ns2,k2,300m\n", encoding="utf-8")
    assert stage_b.radcor_keys(path) == {("s1", "k1"), ("s2", "k2")}
    assert stage_b.radcor_keys(tmp_path / "missing.csv") == set()
    pending: dict[str, list[dict[str, Any]]] = {"stage_b_scores": [{"status": "not yet"}]}
    assert stage_b.summary(pending) == {"status": "not yet"}
    row = {"target": "tss", "evaluation": "nested LOSO (Stage A + B)", "mdsa": 120.04,
           "level": "none", "n": 30.0, "status": stage_b.STATUS["tss"]}  # fmt: skip
    assert stage_b.summary({"stage_b_scores": [row]})["tss"]["mdsa"] == 120.0


def test_stage_b_is_scored_only_when_every_scene_is_decided(tmp_path: Path) -> None:
    (tmp_path / "scenes.csv").write_text("priority,station,key\n1,s,k1\n2,s,k2\n", encoding="utf-8")
    log = "priority,station,key,l1c_folder,status,seconds,note\n"
    (tmp_path / "run-log.csv").write_text(log + "1,s,k1,,ok,1,\n2,s,k2,,not_downloaded,0,\n",
                                          encoding="utf-8")  # fmt: skip
    assert not stage_b.finished(tmp_path)
    (tmp_path / "run-log.csv").write_text(log + "1,s,k1,,ok,1,\n2,s,k2,,failed,3,\n",
                                          encoding="utf-8")  # fmt: skip
    assert not stage_b.finished(tmp_path)  # the MDN has not run yet
    (tmp_path / "windows.csv").write_text("station,key\ns,k1\n", encoding="utf-8")
    digest = hashlib.sha256((tmp_path / "windows.csv").read_bytes()).hexdigest()
    (tmp_path / "mdn-manifest.csv").write_text(f"path,sha256\nwindows.csv,{digest}\n",
                                               encoding="utf-8")  # fmt: skip
    assert stage_b.finished(tmp_path)
