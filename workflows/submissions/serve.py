"""Local single-user submission bridge. GitHub credentials stay in gh's keychain."""

import argparse
import hmac
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
from urllib.parse import parse_qs, urlsplit

from intake import (
    Cohort,
    FIXTURES,
    LANES,
    decode,
    encode,
    private_path,
    receive,
    require,
    signed_in,
    vote_rows,
    gh,
    INBOX,
    submissions,
    original,
)

HERE = Path(__file__).resolve().parent


class Desk:
    def __init__(self, repo, pin, sandbox=None, test_inbox=False):
        from registers import FIRST, ROOT, SEED, member

        if member(ROOT, FIRST, pin) and member(ROOT, pin, "origin/main"):
            from types import SimpleNamespace
            from registers import blob, rows, EV

            records = rows(blob(ROOT, pin, "registers/" + EV))
            self.cohort = SimpleNamespace(
                pin=pin,
                reasons=Cohort(repo, SEED).reasons,
                evidence={r["evidence_id"]: r for r in records},
                lanes={
                    lane: {r["evidence_id"] for r in records if r["use_role"] in roles}
                    for lane, roles in {
                        "T4": {"structural_suitability"},
                        "T3/T6": {"asset_vulnerability", "nbs_effect"},
                    }.items()
                },
            )
        else:
            self.cohort = Cohort(repo, pin)
        self.pin = pin
        self.sandbox = sandbox
        self.test = bool(sandbox) or test_inbox
        self.identity = gh("user")["login"] if sandbox else signed_in()
        if sandbox:
            private_path(sandbox.parent)
            require(not sandbox.is_symlink(), "Invalid test store")
            with self.database() as db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS receipts (number INTEGER PRIMARY KEY, actor TEXT, body TEXT, UNIQUE(actor,body))"
                )

    def recipe_queue(self):
        from registers import ROOT, LIVE, blob, member, FIRST

        require(
            not self.test and member(ROOT, FIRST, self.pin),
            "Use the desk with an official RuralScan revision to review a recipe row",
        )
        if not hasattr(self, "_recipe_queue"):
            self._recipe_queue = json.loads(blob(ROOT, self.pin, LIVE))
        return self._recipe_queue

    def recipe_options(self, params):
        from recipe_rows import TABLES, CANDIDATE, ident, lookup, target
        from registers import ROOT, blob

        queue = self.recipe_queue()
        practice = params.get("practice", [""])[0]
        table = params.get("table", [""])[0]
        record = params.get("record", [""])[0]
        if not practice or table not in TABLES:
            return {
                "practices": sorted(queue["recipes"]),
                "revision": self.pin,
                "actor": self.identity,
            }
        require(practice in queue["recipes"], "Unknown practice")
        if not record:
            return {
                "records": [ident(r) for r in queue["recipes"][practice][TABLES[table]]]
            }
        row = lookup(queue, practice, table, record)
        candidate = json.loads(blob(ROOT, self.pin, CANDIDATE))
        ids = set(row.get("evidence_ids") or [])
        sources = {s["source_id"]: s for s in queue["registers"]["SRC_source_register"]}
        evidence = [
            {
                "id": e["evidence_id"],
                "citation": sources[e["source_id"]].get("citation", e["source_id"]),
                "locator": e.get("locator")
                or (f"page {e['page']}" if e.get("page") else ""),
                "quote": e.get("quote", ""),
            }
            for e in queue["registers"]["EV_evidence_register"]
            if e["evidence_id"] in ids
        ]
        return {
            "row": row,
            "evidence": evidence,
            "reviews": [
                r
                for r in queue["row_reviews"]
                if (r["nbs_id"], r["table"], r["record_id"])
                == (practice, table, record)
            ],
            "target": target(queue, practice, table, record),
            "stale": [
                w
                for w in candidate["stale_wording"].get(practice, [])
                if w["table"] == table and w["record"] == record
            ],
        }

    def submit_row(self, entry):
        from recipe_rows import validate, send

        validate(entry, self.recipe_queue(), self.pin)
        return {"url": send(entry, expected_actor=self.identity)}

    def database(self):
        return sqlite3.connect(self.sandbox, timeout=15)

    def history(self):
        if not self.sandbox:
            result = []
            for issue in reversed(submissions(actor=self.identity)):
                try:
                    item = decode(issue)
                    author = original(issue)
                except (ValueError, RecursionError):
                    continue
                if item["test"] != self.test or item["kind"] == "extraction":
                    continue
                if author != self.identity:
                    continue
                result.append(
                    dict(
                        receipt=issue["number"],
                        lane=item["lane"],
                        kind=item["kind"],
                        payload=item["payload"],
                        url=issue["html_url"],
                    )
                )
            return {"receipts": result}
        with self.database() as db:
            rows = db.execute(
                "SELECT number, body FROM receipts WHERE actor=? ORDER BY number DESC",
                (self.identity,),
            ).fetchall()
        result = []
        for number, body in rows:
            item = decode({"body": body})
            result.append(
                dict(
                    receipt=number,
                    lane=item["lane"],
                    kind=item["kind"],
                    payload=item["payload"],
                )
            )
        return {"receipts": result}

    def submit(self, form):
        kind, lane, payload = form["kind"], form["lane"], form["payload"]
        require(
            form.get("revision") == self.pin,
            "Queue revision differs. Re-open the finding at the selected revision.",
        )
        require(
            kind in {"vote", "csv"} and lane in LANES,
            "Expected an evidence vote or CSV",
        )
        body = encode(kind, lane, self.pin, payload, test=self.test)
        vote_rows(decode({"body": body}), self.identity, self.cohort)
        if self.sandbox:
            require(
                gh("user")["login"] == self.identity,
                "GitHub account changed. Restart the desk.",
            )
            with self.database() as db:
                db.execute(
                    "INSERT OR IGNORE INTO receipts(actor,body) VALUES(?,?)",
                    (self.identity, body),
                )
                (number,) = db.execute(
                    "SELECT number FROM receipts WHERE actor=? AND body=?",
                    (self.identity, body),
                ).fetchone()
            return {"receipt": number, "test": True}
        return {
            "url": receive(
                kind,
                lane,
                self.pin,
                payload,
                expected_actor=self.identity,
                test=self.test,
            )
        }


def handler(desk, origin):
    secret = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, body, mime="application/json", cookie=False):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            )
            if cookie:
                self.send_header(
                    "Set-Cookie", f"rsdesk={secret}; HttpOnly; SameSite=Strict; Path=/"
                )
            self.end_headers()
            self.wfile.write(body)

        def check_host(self):
            require(self.headers.get("Host") == urlsplit(origin).netloc, "Invalid Host")

        def check_session(self):
            cookies = SimpleCookie()
            cookies.load(self.headers.get("Cookie", ""))
            require(
                "rsdesk" in cookies
                and hmac.compare_digest(cookies["rsdesk"].value, secret),
                "Open the desk first",
            )

        def do_GET(self):
            try:
                self.check_host()
                path = urlsplit(self.path).path
                if path in ("/", "/desk.js", "/desk.css", "/rows", "/rows.js"):
                    name, mime = {
                        "/": ("desk.html", "text/html"),
                        "/rows": ("rows.html", "text/html"),
                        "/rows.js": ("rows.js", "text/javascript"),
                        "/desk.js": ("desk.js", "text/javascript"),
                        "/desk.css": ("desk.css", "text/css"),
                    }[path]
                    self.respond(
                        200,
                        (HERE / name).read_bytes(),
                        mime + "; charset=utf-8",
                        cookie=path in ("/", "/rows"),
                    )
                    return
                self.check_session()
                if path == "/api/session":
                    data = dict(
                        actor=desk.identity,
                        revision=desk.pin,
                        test=desk.test,
                        local_only=bool(desk.sandbox),
                        fixtures=FIXTURES,
                        reasons=desk.cohort.reasons,
                    )
                elif path == "/api/rows":
                    data = desk.recipe_options(parse_qs(urlsplit(self.path).query))
                elif path == "/api/history":
                    data = desk.history()
                else:
                    self.send_error(404)
                    return
                self.respond(200, json.dumps(data).encode())
            except (
                ValueError,
                OSError,
                KeyError,
                subprocess.CalledProcessError,
            ) as error:
                self.respond(400, json.dumps({"error": str(error)}).encode())

        def do_POST(self):
            try:
                self.check_host()
                self.check_session()
                require(
                    self.path in ("/api/submit", "/api/rows")
                    and self.headers.get("Origin") == origin
                    and self.headers.get_content_type() == "application/json",
                    "Request must come from the local review form",
                )
                length = int(self.headers.get("Content-Length", "0"))
                require(
                    0 < length <= 65536, "Split this batch into smaller submissions"
                )
                form = json.loads(self.rfile.read(length))
                result = (
                    desk.submit_row(form)
                    if self.path == "/api/rows"
                    else desk.submit(form)
                )
                self.respond(201, json.dumps(result).encode())
            except (
                ValueError,
                OSError,
                KeyError,
                TypeError,
                subprocess.CalledProcessError,
            ) as error:
                self.respond(400, json.dumps({"error": str(error)}).encode())

    return Handler


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ciat-repo", type=Path, required=True)
    p.add_argument("--revision", required=True)
    modes = p.add_mutually_exclusive_group()
    modes.add_argument(
        "--test-inbox",
        action="store_true",
        help="Send only synthetic findings to public RuralScan/evidence issues.",
    )
    modes.add_argument(
        "--sandbox",
        type=Path,
        help="Private SQLite fixture store. Accepts only the two synthetic finding IDs.",
    )
    p.add_argument("--port", type=int, default=8934)
    args = p.parse_args()
    os.umask(0o077)
    desk = Desk(args.ciat_repo, args.revision, args.sandbox, args.test_inbox)
    origin = f"http://127.0.0.1:{args.port}"
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler(desk, origin)) as server:
        print(
            f"{origin} — {desk.identity} — {'local fixture' if args.sandbox else INBOX}",
            flush=True,
        )
        server.serve_forever()


if __name__ == "__main__":
    main()
