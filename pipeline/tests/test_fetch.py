import csv
import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Any

import httpx
import pytest

from climate_pipeline.cli import main
from climate_pipeline.sources import fetch
from climate_pipeline.sources.fetch import Page, Source

SOURCE = Source("doc", "R1", "https://agency.test/doc", "test")


def client(handler: Any) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
        headers={"User-Agent": fetch.USER_AGENT},
    )


def minimal_pdf(pages: list[str]) -> bytes:
    """A small valid PDF with one line of Helvetica text per page (WinAnsi, so accents work)."""
    objects: list[bytes] = []
    kids = " ".join(f"{4 + 2 * k} 0 R" for k in range(len(pages)))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objects.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )
    for k, text in enumerate(pages):
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = b"BT /F1 12 Tf 72 720 Td (" + escaped.encode("cp1252") + b") Tj ET"
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * k} 0 R >>".encode()
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode()
    out += f"startxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


class FakeRunner:
    """Stands in for pdftotext, pdftoppm and tesseract."""

    def __init__(self, pdftotext_out: str) -> None:
        self.pdftotext_out = pdftotext_out
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        self.calls.append(args)
        out = b""
        if args[0] == "pdftotext":
            out = self.pdftotext_out.encode()
        elif args[0] == "tesseract":
            out = "Texto leído por OCR".encode()
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr=b"")


def test_sources_and_keywords_load(tmp_path: Path) -> None:
    path = tmp_path / "sources.csv"
    path.write_text("id,group,url,purpose\na,R1,https://x.test/a,why\n", encoding="utf-8")
    assert fetch.load_sources(path) == [Source("a", "R1", "https://x.test/a", "why")]
    path.write_text("id,group,url,purpose\na,R1,u,p\na,R2,v,q\n", encoding="utf-8")
    with pytest.raises(ValueError, match="repeated"):
        fetch.load_sources(path)
    path.write_text("id,url\na,u\n", encoding="utf-8")
    with pytest.raises(ValueError, match="columns"):
        fetch.load_sources(path)
    words = tmp_path / "keywords.txt"
    words.write_text("# comment\ncaudal ecológico\n\nsedimento*  # prefix\n", encoding="utf-8")
    assert fetch.load_keywords(words) == ["caudal ecológico", "sedimento*"]
    pages = tmp_path / "pages.csv"
    pages.write_text("source_id,pages,reason\na,1-3 7,x\na,2,y\n", encoding="utf-8")
    assert fetch.load_print_pages(pages) == {"a": [1, 2, 3, 7]}


def test_a_fetch_is_saved_with_its_hash_and_an_honest_user_agent(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, html="<html><p>Resolución</p></html>")

    record = fetch.fetch_one(client(handler), SOURCE, tmp_path, max_bytes=10_000)
    assert record.ok and record.status == 200 and record.copy == "live"
    body = Path(record.path).read_bytes()
    assert record.path.endswith(".html") and record.sha256 == hashlib.sha256(body).hexdigest()
    assert record.bytes == len(body) and record.fetched_utc.endswith("+00:00")
    assert "climate-pipeline" in seen[0].headers["user-agent"]


def test_a_redirect_records_the_final_url(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/doc":
            return httpx.Response(301, headers={"location": "https://agency.test/new.pdf"})
        return httpx.Response(200, content=b"%PDF-1.4 fake", headers={"content-type": "x/y"})

    record = fetch.fetch_one(client(handler), SOURCE, tmp_path, max_bytes=10_000)
    assert record.ok and record.final_url == "https://agency.test/new.pdf"
    assert record.requested_url == SOURCE.url and record.path.endswith(".pdf")


def test_an_oversize_body_is_not_saved(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 5000)

    record = fetch.fetch_one(client(handler), SOURCE, tmp_path, max_bytes=1000)
    assert not record.ok and "larger than 1000 bytes" in record.error
    assert not (tmp_path / "raw").exists()


def test_a_refused_page_comes_from_the_archive_labelled_as_such(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "agency.test":
            return httpx.Response(403)
        if request.url.path == "/cdx/search/cdx":
            assert request.url.params["url"] == SOURCE.url
            header = ["urlkey", "timestamp", "original", "mimetype", "statuscode"]
            row = ["test,agency)/doc", "20250101000000", SOURCE.url, "text/html", "200"]
            return httpx.Response(200, json=[header, row])
        assert request.url.path == f"/web/20250101000000id_/{SOURCE.url}"
        return httpx.Response(200, html="<p>archived</p>")

    record = fetch.fetch_one(client(handler), SOURCE, tmp_path, max_bytes=10_000)
    assert record.ok and record.copy == fetch.ARCHIVED
    assert record.archive_timestamp == "20250101000000"
    assert record.requested_url == SOURCE.url and "HTTP 403" in record.error


def test_a_refused_page_without_captures_stays_failed(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "agency.test":
            return httpx.Response(403)
        return httpx.Response(200, json=[])

    record = fetch.fetch_one(client(handler), SOURCE, tmp_path, max_bytes=10_000)
    assert not record.ok and record.copy == "live" and record.error == "HTTP 403"


def test_links_are_absolute_without_fragments_or_repeats() -> None:
    html = """
    <a href="/docs/res-1.pdf">Resolución <b>1</b></a>
    <a href="res-2.pdf#page=3">Two</a>
    <a href="https://other.test/x">X</a>
    <a href="/docs/res-1.pdf">again</a>
    <a href="mailto:a@b.test">mail</a> <a href="#top">top</a> <a href="javascript:void(0)">js</a>
    """
    links = fetch.extract_links(html, "https://agency.test/proyectos/urra")
    assert [(link.url, link.text) for link in links] == [
        ("https://agency.test/docs/res-1.pdf", "Resolución 1"),
        ("https://agency.test/proyectos/res-2.pdf", "Two"),
        ("https://other.test/x", "X"),
    ]
    based = fetch.extract_links('<base href="https://cdn.test/f/"><a href="a.pdf">a</a>', "x")
    assert based[0].url == "https://cdn.test/f/a.pdf"


def test_html_text_keeps_visible_blocks_only() -> None:
    html = "<html><head><style>p{}</style><script>var a=1</script></head><body><h1>Título</h1>"
    html += "<p>Primer   párrafo</p><div>Segundo<br>tercero</div></body></html>"
    assert fetch.html_text(html) == "Título\nPrimer párrafo\nSegundo\ntercero"
    assert fetch.decode_html("ñ".encode("latin-1"), "text/html; charset=ISO-8859-1") == "ñ"


def test_kwic_ignores_accents_case_and_line_breaks() -> None:
    pages = [
        Page(1, "El CAUDAL\n   ECOLÓGICO del río se fija en la resolución."),
        Page(2, "Monitoreos de sedimentos y turbiedad; la física del ICA."),
    ]
    keywords = ["caudal ecológico", "sedimento*", "ICA", "turbidez"]
    hits = fetch.kwic("res", pages, keywords, width=10)
    assert [(h.page, h.keyword) for h in hits] == [
        (1, "caudal ecológico"),
        (2, "sedimento*"),
        (2, "ICA"),
    ]
    # Context comes from the original text, accents kept, whitespace collapsed.
    assert hits[0].context == "El CAUDAL ECOLÓGICO del río s"
    # "física" contains "ica" but is not the word ICA.
    assert hits[2].context.endswith("del ICA.")


def test_ocr_runs_only_on_nearly_empty_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetch, "tool", lambda name: name)
    runner = FakeRunner(
        "Resolución 0838 de 1999, por la cual se otorga una licencia ambiental.\f \f"
    )
    pages = fetch.pdf_pages(Path("doc.pdf"), run=runner)
    assert [p.ocr for p in pages] == [False, True]
    assert pages[1].text == "Texto leído por OCR"
    tools = [call[0] for call in runner.calls]
    assert tools == ["pdftotext", "pdftoppm", "tesseract"]
    assert runner.calls[1][runner.calls[1].index("-f") + 1] == "2"
    assert runner.calls[2][-2:] == ["-l", "spa"]


@pytest.mark.skipif(
    shutil.which("pdftotext") is None, reason="poppler's pdftotext is not installed"
)
def test_real_pdftotext_reads_pages_and_accents(tmp_path: Path) -> None:
    path = tmp_path / "doc.pdf"
    long_line = "Artículo primero: el caudal ecológico mínimo aguas abajo de la presa."
    path.write_bytes(minimal_pdf([long_line, long_line.replace("primero", "segundo")]))
    pages = fetch.pdf_pages(path)
    assert [p.number for p in pages] == [1, 2] and not any(p.ocr for p in pages)
    assert "caudal ecológico mínimo" in pages[0].text and "segundo" in pages[1].text
    hits = fetch.kwic("doc", pages, ["caudal ecologico minimo"])
    assert [h.page for h in hits] == [1, 2]


def test_pages_round_trip_through_the_text_file(tmp_path: Path) -> None:
    pages = [Page(1, "uno\ndos"), Page(2, "", ocr=True), Page(3, "tres")]
    fetch.write_pages(tmp_path / "doc.txt", pages)
    assert fetch.read_pages(tmp_path / "doc.txt") == pages


def html_site(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/a":
        return httpx.Response(200, html='<p>Licencia ambiental</p><a href="/b">b</a>')
    return httpx.Response(404)


def test_fetch_all_writes_text_links_hits_and_manifest(tmp_path: Path) -> None:
    sources = [
        Source("a", "R1", "https://agency.test/a", "page"),
        Source("b", "R1", "https://agency.test/b", "missing"),
    ]
    pauses: list[float] = []

    def offline(request: httpx.Request) -> httpx.Response:
        if request.url.host == "web.archive.org":
            return httpx.Response(200, json=[])
        return html_site(request)

    records, hits = fetch.fetch_all(
        sources, tmp_path, ["licencia ambiental"], client(offline), pause_s=2, sleep=pauses.append
    )
    assert [r.ok for r in records] == [True, False] and pauses == [2]
    assert [(h.source_id, h.page) for h in hits] == [("a", 1)]
    assert (tmp_path / "text" / "a.txt").read_text(encoding="utf-8").startswith("=== page 1 ===")
    with (tmp_path / "links" / "a.csv").open(encoding="utf-8") as handle:
        assert list(csv.reader(handle))[1] == ["https://agency.test/b", "b"]
    with (tmp_path / "manifest.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert tuple(rows[0]) == fetch.MANIFEST_COLUMNS
    assert rows[0]["pages"] == "1" and rows[1]["error"] == "HTTP 404"


def test_a_failed_text_extraction_is_recorded_without_local_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fetch, "tool", lambda name: f"C:/private/{name}.EXE")

    def failing(args: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.CalledProcessError(1, args)

    def pdf(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"%PDF-1.4 truncated")

    records, _ = fetch.fetch_all([SOURCE], tmp_path, [], client(pdf), run=failing)
    assert records[0].ok and records[0].pages == 0
    assert records[0].error == "text extraction failed: pdftotext exited with status 1"


def test_fetch_docs_prints_the_manifest_and_requested_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "s.csv").write_text(
        "id,group,url,purpose\na,R1,https://agency.test/a,p\nz,R2,https://agency.test/z,p\n",
        encoding="utf-8",
    )
    (tmp_path / "k.txt").write_text("licencia\n", encoding="utf-8")
    (tmp_path / "p.csv").write_text("source_id,pages,reason\na,1,quote\n", encoding="utf-8")
    timeouts: list[float] = []

    def make(timeout_s: float = 60.0) -> httpx.Client:
        timeouts.append(timeout_s)
        return client(html_site)

    monkeypatch.setattr(fetch, "make_client", make)
    args = ["fetch-docs", "--sources", str(tmp_path / "s.csv"), "--keywords",
            str(tmp_path / "k.txt"), "--print-pages", str(tmp_path / "p.csv"), "--groups", "R1",
            "--out", str(tmp_path / "out"), "--pause", "0", "--timeout", "300"]  # fmt: skip
    assert main(args) == 0
    assert timeouts == [300.0]
    out = capsys.readouterr().out
    assert "a: ok 200" in out and "z:" not in out
    manifest = out.split(fetch.MANIFEST_BEGIN)[1].split(fetch.MANIFEST_END)[0]
    assert manifest.strip().splitlines()[0] == ",".join(fetch.MANIFEST_COLUMNS)
    assert "=== a page 1 BEGIN ===\nLicencia ambiental\nb\n=== a page 1 END ===" in out
