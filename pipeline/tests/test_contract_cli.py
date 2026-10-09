from pathlib import Path

from climate_pipeline.cli import main
from climate_pipeline.contract import observation as obs


def test_the_cli_writes_the_schema(tmp_path: Path) -> None:
    out = tmp_path / "schema.json"
    assert main(["contract", "schema", "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == obs.schema_text()
