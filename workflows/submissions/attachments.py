"""Read hash-bound review CSVs from prefilled, authenticated GitHub issues."""

import csv
import hashlib
import io
import json
import re
from urllib.parse import urljoin, urlsplit

import requests

HEADER = "RuralScan review submission v2"
MAX_BYTES = 1_000_000
MARKER = r"<!-- ruralscan-review\n(.*?)\n-->"
LINK = r"\[[^\]\n]+\]\((https://github\.com/user-attachments/files/[0-9]+/[^\s)]+\.csv)\)"


def has_header(body):
    """Allow one GitHub CSV upload before the heading, never arbitrary prose."""
    body = body.replace("\r\n", "\n")
    return re.match(r"\A(?:" + LINK + r"\n(?:[ \t]*\n)*)?"
                    + re.escape(HEADER) + r"\n", body) is not None


class AttachmentUnavailable(RuntimeError):
    """Stop the entire preview if a potential opposing ballot cannot be read."""


def require(condition, message):
    if not condition:
        raise ValueError(message)


def download(url, expected_size):
    """No credentials, arbitrary hosts, unbounded bodies or unchecked redirects."""
    with requests.Session() as session:
        session.trust_env = False
        try:
            for _ in range(4):
                parts = urlsplit(url)
                require(parts.scheme == "https" and not parts.username and not parts.password
                        and parts.port in (None, 443), "Invalid attachment address")
                require((parts.hostname == "github.com" and parts.path.startswith("/user-attachments/files/"))
                        or (parts.hostname == "objects.githubusercontent.com"
                            and parts.path.startswith("/github-production-repository-file-")),
                        "Attachment redirect is outside GitHub file storage")
                with session.get(url, timeout=(10, 30), stream=True, allow_redirects=False) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers["Location"])
                        continue
                    response.raise_for_status()
                    if response.headers.get("Content-Length"):
                        require(int(response.headers["Content-Length"]) <= expected_size,
                                "Attachment exceeds its declared size")
                    data = bytearray()
                    for chunk in response.iter_content(16384):
                        data.extend(chunk)
                        require(len(data) <= expected_size, "Attachment exceeds its declared size")
                    return bytes(data)
            raise AttachmentUnavailable("Too many GitHub attachment redirects. Retry before applying any votes.")
        except requests.RequestException as error:
            raise AttachmentUnavailable("Cannot read a review attachment. Retry before applying any votes.") from error


def decode(body, unique_object):
    require(has_header(body), "Unknown review submission format")
    blocks = re.findall(MARKER, body, re.DOTALL)
    require(len(blocks) == 1, "Expected one review submission manifest")
    meta = json.loads(blocks[0], object_pairs_hook=unique_object)
    fields = {"kind", "lane", "revision", "test", "sha256", "bytes", "count"}
    require(isinstance(meta, dict) and set(meta) in (fields, fields | {"payload"}),
            "Malformed review submission manifest")
    require(meta["kind"] == "csv" and isinstance(meta["lane"], str) and meta["lane"] in {"T4", "T3/T6", "M2b", "Mixed"}
            and isinstance(meta["revision"], str) and re.fullmatch(r"[a-f0-9]{40}", meta["revision"])
            and type(meta["test"]) is bool, "Invalid review lane, revision or test flag")
    require(isinstance(meta["sha256"], str) and re.fullmatch(r"[a-f0-9]{64}", meta["sha256"]),
            "Missing CSV content hash")
    require(type(meta["bytes"]) is int and 0 < meta["bytes"] <= MAX_BYTES
            and type(meta["count"]) is int and 0 < meta["count"] <= 20000,
            "Review CSV exceeds its size or row limit")
    links = re.findall(LINK, re.sub(MARKER, "", body, flags=re.DOTALL))
    if "payload" in meta:
        require(isinstance(meta["payload"], str) and not links, "Ambiguous inline and attached CSV")
        data = meta["payload"].encode("utf-8")
    else:
        require(len(links) == 1, "Attach exactly one generated CSV before creating the issue")
        data = download(links[0], meta["bytes"])
    require(len(data) == meta["bytes"] and hashlib.sha256(data).hexdigest() == meta["sha256"],
            "CSV differs from the prepared review batch. Return a fresh submission.")
    payload = data.decode("utf-8-sig")
    require(len(list(csv.DictReader(io.StringIO(payload, newline=""), strict=True))) == meta["count"],
            "CSV row count differs from the prepared review batch")
    return {key: meta[key] for key in ("kind", "lane", "revision", "test")} | {"payload": payload}
