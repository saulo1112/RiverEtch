"""Fetch public documents with a provenance record, and extract their text for quoting.

Used for the regulatory verification of a study reach (``docs/urra-validation/regulatory.md``).
Every request names this project in its User-Agent, waits between requests, keeps TLS
verification on and stops at a size cap. Each fetch is recorded: status, final URL, content type,
bytes, SHA-256 and UTC time. A page the live site refuses may come from the Internet Archive,
always labelled "archived copy". PDFs are read with poppler's ``pdftotext -layout``. Only pages
with almost no text (scanned images) go through OCR (``pdftoppm`` + ``tesseract -l spa``), and
those pages are flagged.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse

import httpx

USER_AGENT = (
    "climate-pipeline/0.1 (research fetch of public documents for a hackathon study; "
    "+https://github.com/saulo1112/RiverEtch)"
)
CDX_URL = "https://web.archive.org/cdx/search/cdx"
ARCHIVED = "archived copy"
MIN_CHARS_PER_PAGE = 50
"""Below this many characters a PDF page is treated as a scanned image and OCRed."""

SOURCE_COLUMNS = ("id", "group", "url", "purpose")
MANIFEST_COLUMNS = (
    "source_id", "group", "requested_url", "final_url", "status", "content_type", "bytes",
    "sha256", "fetched_utc", "copy", "archive_timestamp", "pages", "ocr_pages", "error",
)  # fmt: skip
MANIFEST_BEGIN = "=== FETCH MANIFEST BEGIN ==="
MANIFEST_END = "=== FETCH MANIFEST END ==="

Runner = Callable[..., "subprocess.CompletedProcess[bytes]"]


# ----------------------------------------------------------------------------------------------
# Records
# ----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Source:
    """One document or page to fetch."""

    id: str
    group: str
    url: str
    purpose: str


@dataclass(frozen=True)
class FetchRecord:
    """What one fetch returned (``path`` is the saved body, empty when nothing was saved)."""

    source_id: str
    group: str
    requested_url: str
    final_url: str
    status: int | None
    content_type: str
    bytes: int
    sha256: str
    fetched_utc: str
    copy: str = "live"
    archive_timestamp: str = ""
    path: str = ""
    error: str = ""
    pages: int = 0
    ocr_pages: int = 0

    @property
    def ok(self) -> bool:
        """A 2xx response whose body was saved."""
        return self.status is not None and 200 <= self.status < 300 and bool(self.path)

    def manifest_row(self) -> dict[str, object]:
        """The record as one manifest row.

        Returns:
            Values by manifest column.
        """
        values = asdict(self)
        return {column: values.get(column, "") for column in MANIFEST_COLUMNS}


@dataclass(frozen=True)
class Link:
    """A hyperlink found in an HTML page (absolute URL, fragment removed)."""

    url: str
    text: str


@dataclass(frozen=True)
class Page:
    """The text of one document page; ``ocr`` marks text read from an image."""

    number: int
    text: str
    ocr: bool = False


@dataclass(frozen=True)
class Hit:
    """A keyword found in a document page, with the text around it."""

    source_id: str
    page: int
    keyword: str
    context: str


# ----------------------------------------------------------------------------------------------
# Inputs
# ----------------------------------------------------------------------------------------------


def load_sources(path: Path) -> list[Source]:
    """Read the source list (``id,group,url,purpose``).

    Args:
        path: The CSV file.

    Returns:
        The sources, in file order.

    Raises:
        ValueError: If the header differs or an id repeats.
    """
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != SOURCE_COLUMNS:
            raise ValueError(f"{path}: columns must be {', '.join(SOURCE_COLUMNS)}")
        sources = [Source(**{k: row[k].strip() for k in SOURCE_COLUMNS}) for row in reader]
    ids = [s.id for s in sources]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"{path}: repeated ids {duplicates}")
    return sources


def load_keywords(path: Path) -> list[str]:
    """Read keywords, one per line (``#`` starts a comment; a trailing ``*`` matches a prefix).

    Args:
        path: The keyword file.

    Returns:
        The keywords, in file order.
    """
    words = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.split("#", 1)[0].strip()
        if text:
            words.append(text)
    return words


def load_print_pages(path: Path) -> dict[str, list[int]]:
    """Read the whole pages requested for quoting (``source_id,pages,reason``).

    Args:
        path: The CSV file; ``pages`` is a list such as ``3`` or ``1-2 7``.

    Returns:
        Page numbers by source id.
    """
    pages: dict[str, list[int]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            numbers = pages.setdefault(row["source_id"].strip(), [])
            for part in row["pages"].replace(",", " ").split():
                first, _, last = part.partition("-")
                numbers.extend(range(int(first), int(last or first) + 1))
    return {k: sorted(set(v)) for k, v in pages.items()}


# ----------------------------------------------------------------------------------------------
# Fetching
# ----------------------------------------------------------------------------------------------


def make_client(timeout_s: float = 60.0) -> httpx.Client:
    """An HTTP client with an honest User-Agent, redirects followed and TLS verification on.

    Args:
        timeout_s: Timeout per request.

    Returns:
        The client.
    """
    return httpx.Client(
        headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=timeout_s
    )


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _extension(content_type: str, body: bytes) -> str:
    kind = content_type.lower()
    if body.startswith(b"%PDF") or "pdf" in kind:
        return ".pdf"
    if "html" in kind:
        return ".html"
    if "json" in kind:
        return ".json"
    if "text" in kind or "csv" in kind:
        return ".txt"
    return ".bin"


def fetch_url(
    client: httpx.Client, url: str, dest_stem: Path, max_bytes: int, source: Source
) -> FetchRecord:
    """GET one URL and save its body next to ``dest_stem`` (extension from its type).

    Args:
        client: HTTP client (see :func:`make_client`).
        url: The address.
        dest_stem: Output path without extension.
        max_bytes: Size cap; a larger body is not saved.
        source: The source this fetch belongs to.

    Returns:
        The record (``error`` explains a failure; nothing is saved then).
    """
    base = FetchRecord(source.id, source.group, url, url, None, "", 0, "", _now())
    try:
        with client.stream("GET", url) as response:
            content_type = response.headers.get("content-type", "")
            final = str(response.url)
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    return replace(
                        base,
                        final_url=final,
                        status=response.status_code,
                        content_type=content_type,
                        bytes=total,
                        error=f"larger than {max_bytes} bytes: not saved",
                    )
                chunks.append(chunk)
            body = b"".join(chunks)
            record = replace(
                base,
                final_url=final,
                status=response.status_code,
                content_type=content_type,
                bytes=len(body),
                sha256=hashlib.sha256(body).hexdigest(),
            )
            if not response.is_success:
                return replace(record, error=f"HTTP {response.status_code}")
    except httpx.HTTPError as error:
        return replace(base, error=f"{type(error).__name__}: {error}")
    path = dest_stem.with_suffix(_extension(content_type, body))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return replace(record, path=str(path))


def wayback_fallback(
    client: httpx.Client, url: str, dest_stem: Path, max_bytes: int, source: Source
) -> FetchRecord | None:
    """The latest Internet Archive capture of a URL, fetched raw (``id_``) and labelled.

    Args:
        client: HTTP client.
        url: The original address.
        dest_stem: Output path without extension.
        max_bytes: Size cap.
        source: The source this fetch belongs to.

    Returns:
        The archived copy's record, or None if the archive has no successful capture.
    """
    try:
        response = client.get(
            CDX_URL,
            params={"url": url, "output": "json", "filter": "statuscode:200", "limit": "-5"},
        )
        response.raise_for_status()
        rows: list[list[str]] = response.json() if response.content.strip() else []
    except (httpx.HTTPError, ValueError):
        return None
    if len(rows) < 2:
        return None
    header, latest = rows[0], rows[-1]
    timestamp = latest[header.index("timestamp")]
    original = latest[header.index("original")]
    snapshot = f"https://web.archive.org/web/{timestamp}id_/{original}"
    record = fetch_url(client, snapshot, dest_stem, max_bytes, source)
    return replace(record, requested_url=url, copy=ARCHIVED, archive_timestamp=timestamp)


def fetch_one(
    client: httpx.Client,
    source: Source,
    out_dir: Path,
    max_bytes: int,
    archive: bool = True,
) -> FetchRecord:
    """Fetch a source live, falling back to the Internet Archive when the live fetch fails.

    Args:
        client: HTTP client.
        source: The source.
        out_dir: Where bodies are saved (``<out_dir>/raw/<id>.<ext>``).
        max_bytes: Size cap.
        archive: Try the archive when the live fetch fails.

    Returns:
        The live record, or the archived copy's record (the live error is kept in ``error``).
    """
    stem = out_dir / "raw" / source.id
    live = fetch_url(client, source.url, stem, max_bytes, source)
    if live.ok or not archive or "larger than" in live.error:
        return live
    archived = wayback_fallback(client, source.url, stem, max_bytes, source)
    if archived is None or not archived.ok:
        return live
    return replace(archived, error=f"live fetch failed ({live.error})")


# ----------------------------------------------------------------------------------------------
# HTML
# ----------------------------------------------------------------------------------------------


def decode_html(body: bytes, content_type: str) -> str:
    """Decode an HTML body with its declared charset (header, then meta), else UTF-8.

    Args:
        body: The raw bytes.
        content_type: The Content-Type header.

    Returns:
        The text (undecodable bytes replaced).
    """
    header = re.search(r"charset=([\w-]+)", content_type, re.I)
    meta = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", body[:4096], re.I)
    name = header.group(1) if header else meta.group(1).decode() if meta else "utf-8"
    try:
        return body.decode(name, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


class _LinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[Link] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "base":
            href = dict(attrs).get("href")
            if href:
                self.base_url = urljoin(self.base_url, href)
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._href is None:
            return
        href = self._href.strip()
        self._href = None
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            return
        url = urldefrag(urljoin(self.base_url, href))[0]
        if urlparse(url).scheme in ("http", "https"):
            self.links.append(Link(url, " ".join("".join(self._text).split())))


def extract_links(html: str, base_url: str) -> list[Link]:
    """Every http(s) link of a page, made absolute, in page order, without repeats.

    Args:
        html: The page.
        base_url: The page's own URL (a ``<base href>`` overrides it).

    Returns:
        The links (the first text seen for each URL).
    """
    parser = _LinkParser(base_url)
    parser.feed(html)
    seen: set[str] = set()
    links = []
    for link in parser.links:
        if link.url not in seen:
            seen.add(link.url)
            links.append(link)
    return links


_BLOCK_TAGS = {
    "p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article", "header", "footer",
    "h1", "h2", "h3", "h4", "h5", "h6", "title", "td", "th", "dd", "dt", "blockquote",
}  # fmt: skip
_SKIP_TAGS = {"script", "style", "noscript", "svg", "template"}


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_text(html: str) -> str:
    """The visible text of a page, one block per line, whitespace collapsed.

    Args:
        html: The page.

    Returns:
        The text.
    """
    parser = _TextParser()
    parser.feed(html)
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if line)


# ----------------------------------------------------------------------------------------------
# PDF
# ----------------------------------------------------------------------------------------------


def tool(name: str) -> str:
    """The path of an external program.

    Args:
        name: Program name, e.g. ``pdftotext``.

    Returns:
        Its path.

    Raises:
        FileNotFoundError: If it is not on PATH.
    """
    path = shutil.which(name)
    if path is None:
        raise FileNotFoundError(f"{name} is not installed or not on PATH")
    return path


def needs_ocr(text: str, min_chars: int = MIN_CHARS_PER_PAGE) -> bool:
    """Whether a page's extracted text is too short to be a text layer (a scanned image).

    Args:
        text: The page text from ``pdftotext``.
        min_chars: Threshold in non-blank characters.

    Returns:
        True when the page should be OCRed.
    """
    return len("".join(text.split())) < min_chars


def ocr_page(path: Path, number: int, run: Runner = subprocess.run, lang: str = "spa") -> str:
    """OCR one PDF page: render it at 300 dpi with ``pdftoppm``, read it with ``tesseract``.

    Args:
        path: The PDF.
        number: Page number (1-based).
        run: Subprocess runner (injectable for tests).
        lang: Tesseract language.

    Returns:
        The recognized text.
    """
    with tempfile.TemporaryDirectory() as tmp:
        prefix = Path(tmp) / "page"
        run(
            [tool("pdftoppm"), "-r", "300", "-gray", "-png", "-singlefile",
             "-f", str(number), "-l", str(number), str(path), str(prefix)],
            capture_output=True, check=True,
        )  # fmt: skip
        done = run(
            [tool("tesseract"), str(prefix.with_suffix(".png")), "stdout", "-l", lang],
            capture_output=True,
            check=True,
        )
    return bytes(done.stdout).decode("utf-8", errors="replace")


def pdf_pages(
    path: Path,
    run: Runner = subprocess.run,
    min_chars: int = MIN_CHARS_PER_PAGE,
    lang: str = "spa",
) -> list[Page]:
    """The text of each page of a PDF; nearly empty pages are OCRed and flagged.

    Args:
        path: The PDF.
        run: Subprocess runner (injectable for tests).
        min_chars: Pages with fewer non-blank characters are OCRed.
        lang: OCR language.

    Returns:
        One entry per page.
    """
    done = run(
        [tool("pdftotext"), "-layout", "-enc", "UTF-8", str(path), "-"],
        capture_output=True,
        check=True,
    )
    texts = bytes(done.stdout).decode("utf-8", errors="replace").split("\f")
    if texts and not texts[-1].strip():
        texts = texts[:-1]  # pdftotext ends every page, the last included, with a form feed
    pages = []
    for number, text in enumerate(texts, start=1):
        if needs_ocr(text, min_chars):
            pages.append(Page(number, ocr_page(path, number, run, lang), ocr=True))
        else:
            pages.append(Page(number, text))
    return pages


# ----------------------------------------------------------------------------------------------
# Keyword in context
# ----------------------------------------------------------------------------------------------


def _fold(text: str) -> tuple[str, list[int]]:
    """Accent- and case-folded text with runs of whitespace as one space, and a position map."""
    out: list[str] = []
    where: list[int] = []
    for i, char in enumerate(text):
        if char.isspace():
            if out and out[-1] != " ":
                out.append(" ")
                where.append(i)
            continue
        for part in unicodedata.normalize("NFKD", char):
            if unicodedata.combining(part):
                continue
            for folded in part.casefold():
                out.append(folded)
                where.append(i)
    return "".join(out), where


def fold(text: str) -> str:
    """Text without accents, case-folded, with whitespace runs collapsed to one space.

    Args:
        text: Any text.

    Returns:
        The folded text.
    """
    return _fold(text)[0].strip()


def kwic(
    source_id: str, pages: Sequence[Page], keywords: Iterable[str], width: int = 160
) -> list[Hit]:
    """Find keywords in pages, ignoring accents and case, and keep the text around each hit.

    A keyword matches whole words; one ending in ``*`` matches any word starting with it.

    Args:
        source_id: The document.
        pages: Its pages.
        keywords: Keywords or phrases.
        width: Characters of context kept on each side.

    Returns:
        Hits in page order.
    """
    patterns = []
    for keyword in keywords:
        prefix = keyword.endswith("*")
        folded = fold(keyword.rstrip("*"))
        body = r"\s+".join(re.escape(w) for w in folded.split())
        tail = r"\w*" if prefix else r"(?!\w)"
        patterns.append((keyword, re.compile(rf"(?<!\w){body}{tail}")))
    hits = []
    for page in pages:
        folded, where = _fold(page.text)
        for keyword, pattern in patterns:
            for match in pattern.finditer(folded):
                start = where[match.start()]
                end = where[match.end() - 1] + 1
                context = page.text[max(0, start - width) : end + width]
                hits.append(Hit(source_id, page.number, keyword, " ".join(context.split())))
    return hits


# ----------------------------------------------------------------------------------------------
# Batch
# ----------------------------------------------------------------------------------------------


def manifest_csv(records: Sequence[FetchRecord]) -> str:
    """The fetch manifest as CSV text.

    Args:
        records: Fetch records.

    Returns:
        CSV with :data:`MANIFEST_COLUMNS`.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=MANIFEST_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for record in records:
        writer.writerow(record.manifest_row())
    return buffer.getvalue()


def document_pages(record: FetchRecord, run: Runner = subprocess.run) -> list[Page]:
    """The text of a fetched document: PDF pages, or an HTML page as page 1.

    Args:
        record: A successful fetch.
        run: Subprocess runner for the PDF tools.

    Returns:
        The pages (empty for other content types).
    """
    path = Path(record.path)
    if path.suffix == ".pdf":
        return pdf_pages(path, run)
    if path.suffix == ".html":
        return [Page(1, html_text(decode_html(path.read_bytes(), record.content_type)))]
    if path.suffix in (".txt", ".json"):
        return [Page(1, path.read_text(encoding="utf-8", errors="replace"))]
    return []


def fetch_all(
    sources: Sequence[Source],
    out_dir: Path,
    keywords: Sequence[str],
    client: httpx.Client | None = None,
    max_bytes: int = 60_000_000,
    pause_s: float = 1.5,
    sleep: Callable[[float], Any] = time.sleep,
    run: Runner = subprocess.run,
) -> tuple[list[FetchRecord], list[Hit]]:
    """Fetch sources one by one, extract their text, links and keyword hits.

    Writes ``raw/<id>.<ext>``, ``text/<id>.txt`` (pages separated by ``=== page N ===`` lines),
    ``links/<id>.csv`` for HTML pages, ``kwic.csv`` and ``manifest.csv`` under ``out_dir``.

    Args:
        sources: What to fetch.
        out_dir: Output folder (never committed: it holds whole documents).
        keywords: Keywords for the keyword-in-context table.
        client: HTTP client (default: :func:`make_client`).
        max_bytes: Size cap per document.
        pause_s: Pause between requests, to be gentle with small public servers.
        sleep: Sleep function (injectable for tests).
        run: Subprocess runner for the PDF tools.

    Returns:
        The fetch records (with page counts) and the keyword hits.
    """
    client = client or make_client()
    records: list[FetchRecord] = []
    hits: list[Hit] = []
    for k, source in enumerate(sources):
        if k:
            sleep(pause_s)
        record = fetch_one(client, source, out_dir, max_bytes)
        if record.ok:
            try:
                pages = document_pages(record, run)
            except (OSError, subprocess.CalledProcessError) as error:
                pages = []
                problem = f"text extraction failed: {_describe(error)}"
                record = replace(record, error=f"{record.error}; {problem}".strip("; "))
            record = replace(record, pages=len(pages), ocr_pages=sum(1 for p in pages if p.ocr))
            write_pages(out_dir / "text" / f"{source.id}.txt", pages)
            hits += kwic(source.id, pages, keywords)
            if record.path.endswith(".html"):
                html = decode_html(Path(record.path).read_bytes(), record.content_type)
                write_links(
                    out_dir / "links" / f"{source.id}.csv", extract_links(html, record.final_url)
                )
        records.append(record)
    write_hits(out_dir / "kwic.csv", hits)
    manifest = out_dir / "manifest.csv"
    manifest.write_text(manifest_csv(records), encoding="utf-8", newline="\n")
    return records, hits


def _describe(error: OSError | subprocess.CalledProcessError) -> str:
    """A short reason without local paths (the manifest is committed)."""
    if isinstance(error, subprocess.CalledProcessError):
        command = error.cmd[0] if isinstance(error.cmd, list | tuple) else str(error.cmd)
        return f"{Path(str(command)).stem} exited with status {error.returncode}"
    return type(error).__name__


_PAGE_MARK = re.compile(r"^=== page (\d+)( \(OCR\))? ===$", re.M)


def write_pages(path: Path, pages: Sequence[Page]) -> None:
    """Write a document's pages to one text file, each page under a ``=== page N ===`` line.

    Args:
        path: Output file.
        pages: The pages.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    parts = [f"=== page {p.number}{' (OCR)' if p.ocr else ''} ===\n{p.text}" for p in pages]
    path.write_text("\n".join(parts), encoding="utf-8", newline="\n")


def read_pages(path: Path) -> list[Page]:
    """Read back a file written by :func:`write_pages`.

    Args:
        path: The text file.

    Returns:
        The pages.
    """
    text = path.read_text(encoding="utf-8")
    marks = list(_PAGE_MARK.finditer(text))
    pages = []
    for k, mark in enumerate(marks):
        end = marks[k + 1].start() - 1 if k + 1 < len(marks) else len(text)
        pages.append(Page(int(mark.group(1)), text[mark.end() + 1 : end], bool(mark.group(2))))
    return pages


def write_links(path: Path, links: Sequence[Link]) -> None:
    """Write a page's links as CSV (``url,text``).

    Args:
        path: Output file.
        links: The links.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["url", "text"])
        writer.writerows([link.url, link.text] for link in links)


def write_hits(path: Path, hits: Sequence[Hit]) -> None:
    """Write keyword hits as CSV (``source_id,page,keyword,context``).

    Args:
        path: Output file.
        hits: The hits.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["source_id", "page", "keyword", "context"])
        writer.writerows([h.source_id, h.page, h.keyword, h.context] for h in hits)
