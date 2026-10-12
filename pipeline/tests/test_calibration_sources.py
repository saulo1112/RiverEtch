import csv
import io
import math
from datetime import date
from pathlib import Path

import httpx
import pytest

from climate_pipeline.calibration import sources
from climate_pipeline.calibration.config import load_calibration_config
from climate_pipeline.calibration.fetching import roles
from climate_pipeline.calibration.stations import Candidate

CFG = load_calibration_config(Path(__file__).parents[1] / "calibration.yaml")


def test_recorder_writes_snapshots_and_a_sorted_manifest(tmp_path: Path) -> None:
    rec = sources.Recorder(tmp_path)
    rec.save("b/two.txt", b"2", "https://x.test/2")
    rec.save("a/one.txt", b"1", "https://x.test/1", note="subset")
    rec.fail("https://x.test/3", "timeout")
    assert (tmp_path / "a" / "one.txt").read_bytes() == b"1"
    rows = list(csv.DictReader(io.StringIO(rec.manifest())))
    assert [r["path"] for r in rows] == ["", "a/one.txt", "b/two.txt"]
    assert rows[1]["sha256"] == "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b"
    assert rows[0]["note"] == "failed: timeout" and rec.failures == ["https://x.test/3: timeout"]


def test_recorder_keeps_an_earlier_snapshot_with_its_file_time(tmp_path: Path) -> None:
    import os

    (tmp_path / "rain").mkdir()
    (tmp_path / "rain" / "kept.csv").write_bytes(b"1")
    os.utime(tmp_path / "rain" / "kept.csv", (1_760_000_000, 1_760_000_000))
    rec = sources.Recorder(tmp_path)
    assert rec.keep("rain/kept.csv", "https://x.test/k", "kept") == b"1"
    row = next(csv.DictReader(io.StringIO(rec.manifest())))
    assert row["path"] == "rain/kept.csv" and row["fetched_utc"] == "2025-10-09T08:53:20+00:00"
    assert row["sha256"].startswith("6b86b273") and row["note"] == "kept"


def test_period_lines_keep_the_header_and_the_period_verbatim() -> None:
    body = (b"fechaObservacion,valorObservado,nivelAprobacion\r\n"
            b"2018-01-01 00:00:00,1.5,900\r\n2019-03-02 00:00:00,2,900\r\n"
            b"2027-01-01 00:00:00,3,900\r\n")  # fmt: skip
    out = sources.period_lines(body, date(2018, 12, 1), date(2026, 9, 30))
    assert out == (b"fechaObservacion,valorObservado,nivelAprobacion\r\n"
                   b"2019-03-02 00:00:00,2,900\r\n")  # fmt: skip


def test_get_retries_once_then_raises() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500 if calls["n"] == 1 else 200, content=b"ok")

    assert sources.get(httpx.Client(transport=httpx.MockTransport(handler)), "https://x") == b"ok"
    always = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    with pytest.raises(httpx.HTTPStatusError):
        sources.get(always, "https://x")


def test_chirps_days_record_unreadable_days() -> None:
    def reader(url: str, points: list[tuple[float, float]]) -> list[float]:
        if "2024.01.02" in url:
            raise OSError("no file")
        return [1.0] * len(points)

    rows, failed = sources.chirps_days(
        "https://c.test/{year}/chirps-v2.0.{date}.cog", [("g1", -74.0, 5.0)],
        date(2024, 1, 1), date(2024, 1, 3), reader, 2,
    )  # fmt: skip
    assert failed == ["2024-01-02"] and len(rows) == 3
    assert rows[0] == {"date": "2024-01-01", "g1": 1.0} and math.isnan(float(str(rows[1]["g1"])))


def test_acolite_urls_are_pinned_and_roles_follow_the_files() -> None:
    assert sources.ACOLITE_COMMIT in sources.acolite_file_url("data/x.txt")
    cand = Candidate("1", "n", -73.9, 7.4, "catalog", quality_point="p",
                     files={"CM_D": 1, "Q_MEDIA_D": 2, "TR_QS_M": 3})  # fmt: skip
    assert roles(cand, CFG, (-74.0, 7.3, -73.8, 7.5)) == [
        "samples", "cm_d", "flow", "transport", "reach"
    ]  # fmt: skip
    far = Candidate("2", "n", -75.0, 3.0, "catalog")
    assert roles(far, CFG, (-74.0, 7.3, -73.8, 7.5)) == []


def test_read_errors_are_classified() -> None:
    from climate_pipeline.calibration.fetching import error_kind, error_rows

    permanent = "S2B_18NUH_20240123_0_L2A scl: '/vsis3/sentinel-s2-l2a/tiles/x.jp2' does not exist"
    assert error_kind(permanent) == "permanent"
    assert error_kind("S2A_x red: CURL error: Could not resolve host") == "transient"
    rows = error_rows([permanent, permanent, "b: timeout"])
    assert [r["kind"] for r in rows] == ["permanent", "transient"]
