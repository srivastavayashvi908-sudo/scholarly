"""Look up paper metadata from a DOI (Crossref) or an arXiv ID (arXiv API). Both are free, no key."""
import html
import re
import xml.etree.ElementTree as ET

import httpx
from fastapi import HTTPException

HEADERS = {"User-Agent": "Scholarly/1.0 (student DBMS project)"}

ARXIV_RE = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf)/|10\.48550/arxiv\.|^arxiv:|^)(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?(?:\.pdf)?$",
    re.IGNORECASE,
)
DOI_RE = re.compile(r"(10\.\d{4,9}/\S+)")


def parse_identifier(raw: str) -> tuple[str, str]:
    """Return ('arxiv', id) or ('doi', doi)."""
    s = raw.strip().rstrip("/")
    m = ARXIV_RE.search(s)
    if m:
        return "arxiv", m.group(1)
    m = DOI_RE.search(s)
    if m:
        return "doi", m.group(1).lower()
    raise HTTPException(400, "That doesn't look like a DOI (10.xxxx/...) or an arXiv ID/link")


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"<[^>]+>", " ", text)          # strip JATS/XML tags from Crossref abstracts
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return re.sub(r"^abstract\s*", "", text, flags=re.IGNORECASE) or None


def fetch_crossref(doi: str) -> dict:
    try:
        r = httpx.get(f"https://api.crossref.org/works/{doi}", headers=HEADERS, timeout=20)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Couldn't reach Crossref: {e}")
    if r.status_code == 404:
        raise HTTPException(404, f"DOI {doi} wasn't found on Crossref")
    r.raise_for_status()
    w = r.json()["message"]
    authors = ", ".join(
        " ".join(p for p in (a.get("given"), a.get("family")) if p) or a.get("name", "")
        for a in w.get("author", [])
    )
    date_parts = (w.get("issued") or w.get("published") or {}).get("date-parts") or [[None]]
    pdf_url = next(
        (l["URL"] for l in w.get("link", []) if l.get("content-type") == "application/pdf"), None
    )
    return {
        "title": _clean(": ".join([(w.get("title") or ["Untitled"])[0], *(w.get("subtitle") or [])[:1]])),
        "authors": authors or None,
        "year": date_parts[0][0],
        "venue": _clean((w.get("container-title") or [None])[0]),
        "doi": doi,
        "arxiv_id": None,
        "abstract": _clean(w.get("abstract")),
        "pdf_url": pdf_url,
        "references": sorted({ref["DOI"].lower() for ref in w.get("reference", []) if ref.get("DOI")}),
    }


def fetch_arxiv(arxiv_id: str) -> dict:
    try:
        r = httpx.get(
            "https://export.arxiv.org/api/query",
            params={"id_list": arxiv_id},
            headers=HEADERS,
            timeout=20,
            follow_redirects=True,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Couldn't reach arXiv: {e}")
    ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    entry = ET.fromstring(r.text).find("a:entry", ns)
    if entry is None or entry.find("a:title", ns) is None:
        raise HTTPException(404, f"arXiv paper {arxiv_id} wasn't found")
    doi_el = entry.find("arxiv:doi", ns)
    journal_el = entry.find("arxiv:journal_ref", ns)
    return {
        "title": _clean(entry.findtext("a:title", namespaces=ns)),
        "authors": ", ".join(a.findtext("a:name", namespaces=ns) for a in entry.findall("a:author", ns)),
        "year": int(entry.findtext("a:published", namespaces=ns)[:4]),
        "venue": _clean(journal_el.text) if journal_el is not None else "arXiv",
        "doi": doi_el.text.lower() if doi_el is not None else f"10.48550/arxiv.{arxiv_id}".lower(),
        "arxiv_id": arxiv_id,
        "abstract": _clean(entry.findtext("a:summary", namespaces=ns)),
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
        "references": [],
    }


def download_pdf(url: str) -> bytes:
    try:
        r = httpx.get(url, headers=HEADERS, timeout=60, follow_redirects=True)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Couldn't download the PDF: {e}")
    if not r.content.startswith(b"%PDF"):
        raise HTTPException(422, "That URL didn't return a PDF file (it may be behind a paywall)")
    return r.content
