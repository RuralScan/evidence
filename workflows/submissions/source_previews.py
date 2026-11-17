"""Build hosted finding previews from the current register and locally acquired originals."""

import argparse
import hashlib
import io
import json
import re
import unicodedata
from collections import defaultdict
from functools import cache, lru_cache
from html.parser import HTMLParser
from pathlib import Path

import fitz
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
EXCLUDED = {"wb_fsrp_2022", "wb_kcsap_2016", "mushtaq_2023"}
PUBLIC = {"open_access", "oa", "open", "green", "gold", "hybrid"}


def publishable(source):
    license_text = (source.get("license") or "").lower()
    return (
        source["source_id"] not in EXCLUDED
        and source.get("access_status") in PUBLIC
        and "internal" not in license_text
        and "-nd" not in license_text
    )


def signature(ev, src):
    values = [
        ev.get(k)
        for k in (
            "source_id",
            "page",
            "locator_type",
            "locator",
            "quote",
            "claim_basis",
        )
    ]
    values += [
        src.get(k) for k in ("url", "library_path", "access_status", "license", "doi")
    ]
    data = json.dumps(
        [str(v or "") for v in values], ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(data.encode()).hexdigest()


def normalize(text):
    text = unicodedata.normalize("NFKC", text).replace("\u00ad", "")
    return " ".join(re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text).split())


def anchors(quote):
    words = quote.split()
    if not words:
        return []
    phrases = [quote]
    if len(words) > 10:
        for offset in (0, (len(words) - 10) // 2, len(words) - 10):
            phrases.append(" ".join(words[offset : offset + 10]))
    return list(dict.fromkeys(phrases))


def excerpt(text, phrases):
    for phrase in phrases:
        start = text.find(phrase)
        if start >= 0:
            end = start + len(phrase)
            return {
                "before": text[max(0, start - 120) : start],
                "match": text[start:end],
                "after": text[end : end + 120],
                "partial": phrase != phrases[0],
            }
    return {}


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden = True

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = False

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def web_previews(corpus, sid, findings, src, index):
    for ext in (".md", ".txt", ".html"):
        snapshot = corpus / (sid + ext)
        if not snapshot.is_file():
            continue
        raw = snapshot.read_text(encoding="utf-8", errors="replace")
        if ext == ".html":
            parser = VisibleText()
            parser.feed(raw)
            raw = " ".join(parser.parts)
        text = normalize(raw)
        for ev in findings:
            if ev.get("locator_type") != "section" or ev["evidence_id"] in index:
                continue
            quote = normalize(ev.get("quote") or "")
            if len(quote) < 12 or text.count(quote) != 1:
                continue
            index[ev["evidence_id"]] = dict(
                key=signature(ev, src),
                locator=ev.get("locator"),
                **excerpt(text, [quote]),
            )


def build(queue, corpus, dest, *, updated=None):
    dest.mkdir(parents=True, exist_ok=True)
    manifest = dest / "index.json"
    index = (
        json.loads(manifest.read_bytes())
        if updated is not None and manifest.is_file()
        else {}
    )
    old_images = {item["image"] for item in index.values() if "image" in item}
    for eid in updated or ():
        index.pop(eid, None)
    grouped = defaultdict(list)
    sources = {s["source_id"]: s for s in queue["registers"]["SRC_source_register"]}
    for ev in queue["registers"]["EV_evidence_register"]:
        if updated is None or ev["evidence_id"] in updated:
            grouped[ev["source_id"]].append(ev)
    for sid, findings in sorted(grouped.items()):
        src = sources[sid]
        pdf = corpus / (sid + ".pdf")
        if not publishable(src):
            continue
        web_previews(corpus, sid, findings, src, index)
        if not pdf.is_file():
            continue
        with fitz.open(pdf) as doc:
            if not doc.is_pdf or doc.needs_pass:
                continue

            @cache
            def page_text(n, sorted_text=False):
                return normalize(doc[n].get_text(sort=sorted_text))

            for ev in findings:
                quote = normalize(ev.get("quote") or "")
                if len(quote) < 12 or ev.get("locator_type") == "file_line":
                    continue
                phrases = anchors(quote)
                n = ev.get("page")
                if n is None:
                    # A section locator alone is insufficient to select a PDF page.
                    pages = [
                        p
                        for p in range(len(doc))
                        if quote in page_text(p) or quote in page_text(p, True)
                    ]
                    if len(pages) != 1:
                        continue
                    n = pages[0] + 1
                if not isinstance(n, int) or not 1 <= n <= len(doc):
                    continue
                original = ev.get("quote") or ""
                is_table = ev.get("claim_basis") in {"table", "figure_read"} or (
                    original.count("\n") >= 3 and len(re.findall(r"\d", original)) >= 4
                )
                item = {"key": signature(ev, src), "page": n}
                match = excerpt(page_text(n - 1), phrases)
                if not match or match["partial"]:
                    alternative = excerpt(page_text(n - 1, True), phrases)
                    if alternative and (not match or not alternative["partial"]):
                        match = alternative
                item.update(match)
                if is_table:
                    page = doc[n - 1]
                    rects = []
                    for phrase in phrases:
                        rects = page.search_for(phrase)
                        if rects:
                            break
                    if rects and not page.rotation:
                        region = fitz.Rect(rects[0])
                        for rect in rects[1:]:
                            region |= rect
                        # Keep adjacent rows, headings and both sides of the table in view.
                        clip = (
                            fitz.Rect(
                                page.rect.x0,
                                region.y0 - 95,
                                page.rect.x1,
                                region.y1 + 40,
                            )
                            & page.rect
                        )
                        pix = page.get_pixmap(
                            matrix=fitz.Matrix(1.8, 1.8), clip=clip, alpha=False
                        )
                        encoded = io.BytesIO()
                        Image.frombytes(
                            "RGB", (pix.width, pix.height), pix.samples
                        ).save(encoded, format="WEBP", quality=80, method=3)
                        data = encoded.getvalue()
                        filename = hashlib.sha256(data).hexdigest() + ".webp"
                        image_dir = dest / "pages"
                        image_dir.mkdir(exist_ok=True)
                        (image_dir / filename).write_bytes(data)
                        item["image"] = filename
                        item["boxes"] = [
                            [
                                round(v, 5)
                                for v in (
                                    (r.x0 - clip.x0) / clip.width,
                                    (r.y0 - clip.y0) / clip.height,
                                    r.width / clip.width,
                                    r.height / clip.height,
                                )
                            ]
                            for r in rects
                        ]
                if not match and "image" not in item:
                    continue
                index[ev["evidence_id"]] = item
            page_text.cache_clear()
    manifest.write_text(
        json.dumps(index, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    )
    used = {item["image"] for item in index.values() if "image" in item}
    for name in old_images - used:
        if re.fullmatch(r"[0-9a-f]{64}\.webp", name):
            (dest / "pages" / name).unlink(missing_ok=True)
    return len(index)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument(
        "--out", required=True, type=Path, help="Use a fresh output directory"
    )
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Choose a fresh output directory")
    queue = json.loads((ROOT / "publication/review-queue.json").read_bytes())
    print(f"Prepared {build(queue, args.corpus, args.out)} finding previews")
