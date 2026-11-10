"""Exercise CIAT review and clarification on three synthetic records."""

import csv
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

SITING = "training_contour_tree_siting"
SITE_ONLY = "training_plot_description"
SPECIES = "training_species_envelope"
REVIEWER = "training_reviewer"
QUESTION = "Does this siting statement establish a numerical slope cutoff?"
TAXON = "Faidherbia albida"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_fields(pairs):
    fields = {}
    for name, value in pairs:
        require(name not in fields, "Repeated field in review answer sheet")
        fields[name] = value
    return fields


def read_answers(path):
    source = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=unique_fields
    )
    require(
        isinstance(source, dict) and set(source) == {"votes"},
        "Expected a JSON object with a votes list",
    )
    votes = source["votes"]
    expected = {
        SITING: {"decision": "ok"},
        SITE_ONLY: {"decision": "drop", "reason": "off_scope"},
        SPECIES: {
            "decision": "reclassify",
            "reason": "species_envelope",
            "claim_scope": "species_specific",
            "taxon": TAXON,
        },
    }
    feedback = {
        SITING: "The answer supports keeping the observation. Leave its numerical calibration open.",
        SITE_ONLY: "A sample-plot description belongs on a coded off-scope soft drop.",
        SPECIES: "Keep the named species envelope through species-specific reclassification.",
    }
    require(
        isinstance(votes, list) and len(votes) == len(expected),
        "Supply one vote for each of the three training claims",
    )
    seen = set()
    for vote in votes:
        require(isinstance(vote, dict), "Expected a JSON object for each vote")
        eid = vote.get("evidence_id")
        require(
            isinstance(eid, str) and eid in expected, "Unknown training evidence ID"
        )
        require(eid not in seen, f"Duplicate vote for {eid}")
        seen.add(eid)
        require(
            all(vote.get(k) == v for k, v in expected[eid].items()),
            f"{eid}: {feedback[eid]}",
        )
        require(
            set(vote) == {"note", "evidence_id"} | expected[eid].keys(),
            f"{eid}: check fields for this decision",
        )
        note = vote["note"]
        require(
            isinstance(note, str) and note.strip(),
            f"{eid}: include a written reason in note",
        )
    return votes


def csv_rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def check_reply_preserved_review(paths, pending_evidence, pending_log):
    require(
        paths.evidence.read_bytes() == pending_evidence
        and paths.review_log.read_bytes() == pending_log,
        "Reply or answer changed the evidence or review log",
    )


def seed_register(path):
    """Synthetic excerpts written for this exercise. No published source is quoted."""
    records = [
        (SITING, "slope", "Contour planting is described on gentle slopes."),
        (SITE_ONLY, "slope", "The sampling plot was on a hillside."),
        (
            SPECIES,
            "annual_precipitation",
            "The rainfall envelope applies only to Faidherbia albida.",
        ),
    ]
    path.parent.mkdir(parents=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "evidence_id",
                "source_id",
                "use_role",
                "variable",
                "page",
                "quote",
                "relationship",
                "attribution",
                "review_state",
                "reviewer_ok",
                "claim_scope",
                "taxon",
            ),
            lineterminator="\n",
        )
        writer.writeheader()
        for number, (eid, variable, quote) in enumerate(records, 1):
            writer.writerow(
                dict(
                    evidence_id=eid,
                    source_id="training_source",
                    use_role="structural_suitability",
                    variable=variable,
                    page=number,
                    quote=quote,
                    relationship="{}",
                    attribution="Synthetic training passage",
                    reviewer_ok="false",
                    claim_scope="practice_technology",
                )
            )


def lesson(root, final_votes):
    from nbs_ruralscan.schema_tools import clarifications
    from nbs_ruralscan.schema_tools.review_local import save_decision
    from nbs_ruralscan.schema_tools.submit_review import replay

    paths = clarifications.ClarificationPaths.from_root(root)
    seed_register(paths.evidence)
    paths.decisions.parent.mkdir(parents=True)

    def siting_question():
        matches = [
            issue
            for issue in clarifications.build(paths)
            if issue["reviewer"] == REVIEWER
            and issue["question"] == QUESTION
            and [item["evidence_id"] for item in issue["records"]] == [SITING]
        ]
        require(len(matches) == 1, "Expected one question linked to the siting record")
        return matches[0]

    save_decision(
        paths,
        dict(
            evidence_id=SITING,
            reviewer=REVIEWER,
            decision="query",
            reason="insufficient_context",
            note=QUESTION,
        ),
    )
    replay(root)
    issue = siting_question()
    require(
        issue["status"] == "needs_investigation", "Expected a pending investigation"
    )
    pending_row = next(
        row for row in csv_rows(paths.evidence) if row["evidence_id"] == SITING
    )
    require(
        pending_row["reviewer_ok"] == "false", "Query prematurely approved the claim"
    )
    pending_evidence = paths.evidence.read_bytes()
    pending_log = paths.review_log.read_bytes()

    # A threaded reply requests source checking. Submitting the exchange alone
    # must leave the evidence register and review log exactly as they were.
    reply = clarifications.record(
        paths,
        dict(
            issue_id=issue["id"],
            fingerprint=issue["fingerprint"],
            evidence_id=SITING,
            reviewer=REVIEWER,
            action="reply",
            note="Please check whether the page specifies an angle.",
        ),
    )
    replay(root)
    require(
        clarifications.shared_events(paths) == [reply]
        and reply["evidence_ids"] == [SITING]
        and reply["action"] == "reply"
        and reply["issue_id"] == issue["id"]
        and reply["fingerprint"] == issue["fingerprint"],
        "Reply was not published exactly once against its issue and record",
    )
    require(
        siting_question()["status"] == "needs_investigation", "Reply closed the query"
    )
    check_reply_preserved_review(paths, pending_evidence, pending_log)

    # Simulate the investigator's source-checked follow-up, using the field
    # fingerprint that the dashboard checks before making the answer available.
    paths.followups.parent.mkdir(parents=True)
    answer = dict(
        evidence_id=SITING,
        reviewer=REVIEWER,
        note=QUESTION,
        status="resolved",
        resolution="The synthetic passage describes gentle slopes and supplies no numerical cutoff.",
        resolution_checks=[
            dict(
                evidence_id=SITING,
                field="quote",
                sha256=sha256(pending_row["quote"].encode()).hexdigest(),
            )
        ],
    )
    paths.followups.write_text(json.dumps({SITING: answer}), encoding="utf-8")
    answered = siting_question()
    require(
        answered["status"] == "answer_ready"
        and [item["response"] for item in answered["answers"]]
        == [answer["resolution"]],
        "Source-checked answer missing from the open question",
    )
    check_reply_preserved_review(paths, pending_evidence, pending_log)

    for final_vote in final_votes:
        save_decision(paths, {**final_vote, "reviewer": REVIEWER})
    replay(root)
    rows = {row["evidence_id"]: row for row in csv_rows(paths.evidence)}
    require(
        list(rows) == [SITING, SITE_ONLY, SPECIES],
        "Review lost or reordered a training record",
    )
    require(
        rows[SITING]["reviewer_ok"] == "true"
        and rows[SITING]["review_state"] == ""
        and rows[SITING]["relationship"] == pending_row["relationship"]
        and siting_question()["status"] == "resolved",
        "Keep failed to resolve the question",
    )
    require(
        rows[SITE_ONLY]["review_state"] == "dropped",
        "Site description was not soft-dropped",
    )
    require(
        rows[SPECIES]["claim_scope"] == "species_specific"
        and rows[SPECIES]["taxon"] == TAXON
        and rows[SPECIES]["review_state"] == ""
        and rows[SPECIES]["reviewer_ok"] == "true",
        "Species-specific claim was not retained and reclassified",
    )
    events = [(r["evidence_id"], r["decision"]) for r in csv_rows(paths.review_log)]
    require(
        events
        == [
            (SITING, "query"),
            (SITING, "ok"),
            (SITE_ONLY, "drop"),
            (SPECIES, "reclassify"),
        ],
        "Unexpected order or count of review decisions",
    )
    require(
        clarifications.shared_events(paths) == [reply],
        "Final decisions changed the reply history",
    )

    records = (
        paths.evidence,
        paths.review_log,
        paths.history,
        paths.decisions,
        paths.pending,
        paths.followups,
    )
    before_retry = [p.read_bytes() for p in records]
    replay(root)
    require(
        before_retry == [p.read_bytes() for p in records],
        "Retry changed a training record",
    )
    return dict(
        synthetic_evidence_rows=len(rows),
        query_then_linked_reply=True,
        answer_ready_before_keep=True,
        approval_after_reply=False,
        question_status_after_keep="resolved",
        soft_dropped_rows=1,
        species_reclassified_and_retained=1,
        review_log_events=len(events),
        clarification_events=1,
        retry_byte_identical=True,
    )


def main():
    if len(sys.argv) not in (2, 3):
        raise ValueError(
            "Expected the pinned CIAT src directory and optional review answer sheet"
        )
    src = Path(sys.argv[1])
    require(
        src.is_absolute()
        and (src / "nbs_ruralscan/schema_tools/submit_review.py").is_file(),
        "Expected an absolute path to the pinned CIAT src directory",
    )
    sheet = (
        Path(sys.argv[2])
        if len(sys.argv) == 3
        else Path(__file__).with_name("review-answers.json")
    )
    votes = read_answers(sheet)
    sys.path.insert(0, str(src))
    with TemporaryDirectory(prefix="ruralscan-training-review-") as temporary:
        work = Path(temporary)
        home = work / "user"
        home.mkdir()
        # CIAT creates a per-user review lock. Isolate it for direct calls too.
        with patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)}):
            print(json.dumps(lesson(work / "records", votes)))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        sys.exit(str(error))
