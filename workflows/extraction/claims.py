"""Build one unreviewed, page-anchored EvidenceUnit for CIAT intake.

Source-defined parameters and observations retain separate meanings. Reviewing a
unit, designing a recipe and correcting a historical row happen downstream.
"""

from copy import deepcopy
from decimal import Decimal
import json
import math
import re


RULESET = "v1.9.9"
SCOPE_FIELDS = ("nbs_id", "suitability_family_id", "variable", "use_role")
ROLES = {
    "structural_suitability",
    "operational_risk",
    "nbs_effect",
    "asset_vulnerability",
}
EFFECTS = {"nbs_effect", "asset_vulnerability"}
CHOICES = {
    "evidence_type": {
        "literature_relationship",
        "ml_importance",
        "scoping_candidate",
        "expert",
    },
    "claim_basis": {
        "primary_measured",
        "modelled",
        "cited_secondary",
        "expert_assertion",
        "table",
        "figure_read",
    },
    "claim_scope": {"practice_technology", "species_specific", "crop_specific"},
    "extraction_confidence": {"high", "medium", "low"},
}
TEXT_FIELDS = {"raw_name", "taxon", "lineage_of", "attribution", "observed_dataset"}
EFFECT_TEXT = {
    "direction",
    "direction_cue",
    "outcome_raw",
    "strength_class",
    "metric",
    "unit",
    "framing",
    "significance",
    "design",
}
EFFECT_NUMBERS = {"magnitude", "magnitude_low", "magnitude_high", "n"}
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
# A hyphen after a digit separates endpoints; a leading minus denotes a signed value.
NUMBER = re.compile(
    r"(?<![\w.])[+\-−]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?"
)


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value


def identifier(value, label):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError(f"Invalid {label}")
    return value


def subset(value, fields, label):
    if not isinstance(value, dict) or set(value) - fields:
        raise ValueError(f"Unsupported fields in {label}")


def choice(value, choices, field):
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"Invalid {field}")


def numbers(text):
    return {
        Decimal(m.group().replace(",", "").replace("−", "-"))
        for m in NUMBER.finditer(text)
    }


def ground(value, anchors, field):
    """Check nested source-reported numbers, including numeric tokens in labels."""
    if isinstance(value, dict):
        for child in value.values():
            ground(child, anchors, field)
    elif isinstance(value, list):
        for child in value:
            ground(child, anchors, field)
    elif type(value) in (int, float):
        if (type(value) is float and not math.isfinite(value)) or Decimal(
            str(value)
        ) not in anchors:
            raise ValueError(f"{field}: numeric value missing from quote or nonfinite")
    elif isinstance(value, str):
        if not numbers(value) <= anchors:
            raise ValueError(f"{field}: numeric text missing from quote")
    else:
        raise ValueError(f"{field}: expected source text or number")


def effect_relationship(rel, quote):
    subset(rel, EFFECT_TEXT | EFFECT_NUMBERS, "effect relationship")
    for key in rel.keys() & EFFECT_TEXT:
        nonempty(rel[key], key)
    for key in rel.keys() & EFFECT_NUMBERS:
        if type(rel[key]) not in (int, float):
            raise ValueError(f"{key} must be numeric")
    if "n" in rel and (type(rel["n"]) is not int or rel["n"] < 1):
        raise ValueError("n must be a positive integer")
    if "direction" in rel:
        choice(rel["direction"], {"positive", "negative", "none"}, "effect direction")
        cue = nonempty(rel.get("direction_cue"), "direction_cue")
        if cue not in quote:
            raise ValueError("Effect direction cue must occur in located quote")
    elif "direction_cue" in rel:
        raise ValueError("Direction cue requires direction")
    if "framing" in rel:
        choice(rel["framing"], {"presence", "loss"}, "framing")
    metric = nonempty(rel.get("metric"), "metric")
    nonempty(rel.get("outcome_raw"), "outcome_raw")
    choice(
        metric,
        {
            "smd_hedges_g",
            "pct_change",
            "ln_response_ratio",
            "absolute",
            "ordinal_rating",
            "narrative",
        },
        "metric",
    )
    for key, choices in (
        ("strength_class", {"slight", "moderate", "strong", "unspecified"}),
        ("significance", {"sig", "ns", "not_reported"}),
        (
            "design",
            {
                "meta_analysis",
                "rct",
                "quasi_experimental",
                "observational",
                "model",
                "case_study",
                "expert",
                "practitioner_rating",
            },
        ),
    ):
        if key in rel:
            choice(rel[key], choices, key)
    if metric == "pct_change" and "magnitude" in rel:
        percent_anchor(rel["magnitude"], quote)
    if metric == "absolute":
        nonempty(rel.get("unit"), "absolute effect unit")
    if metric == "narrative" and (
        rel.keys() & {"magnitude", "magnitude_low", "magnitude_high"}
    ):
        raise ValueError("Narrative evidence cannot carry a quantified magnitude")
    if (
        metric == "narrative"
        and rel.get("strength_class", "unspecified") != "unspecified"
    ):
        raise ValueError(
            "Narrative evidence cannot assign a strength class from adjectives"
        )
    if (
        "magnitude_low" in rel
        and "magnitude_high" in rel
        and rel["magnitude_low"] > rel["magnitude_high"]
    ):
        raise ValueError("Effect interval endpoints are reversed")


# Source-only fields from the T4 evidence contract. Runtime mappings are downstream.
PARAMETERS = {"abs_min", "abs_max", "opt_low", "opt_high", "threshold"}
WEIGHTS = {"weight", "ahp_weight_pct"}
COMMON_CONTEXT = set(
    """practice_as_described country region aez farming_system income_group
climate_zone hazard_type hazard_severity severity_cue hazard_magnitude comparator gas attribution
bundle_components component_share_pct component_share_kind nbs_component normal_year_reference
counterfactual unreplicated ocr_text beneficiary landscape_scale_only timescale_of_effect envelope_misfit
cost_nature note""".split()
)
T4_CONTEXT = {
    "reported_values",
    "calibration_hold",
    "source_check",
    "model_use",
    "model_use_provenance",
    "vertical_reference",
    "spatial_support",
    "observed_dataset",
    "applicability_hold",
    "intended_use",
}


def numeric(value, field):
    if type(value) not in (int, float) or (
        type(value) is float and not math.isfinite(value)
    ):
        raise ValueError(f"{field} must be a finite number")


def percent_anchor(value, text):
    matches = (
        match
        for match in NUMBER.finditer(text)
        if re.match(
            r"\s*(?:[%％]|percent\b|per cent\b|pour cent\b|por ciento\b)",
            text[match.end() :],
            re.I,
        )
    )
    if not any(numbers(match.group()) == {Decimal(str(value))} for match in matches):
        raise ValueError(
            "Percentage needs its value and percentage unit in the source excerpt"
        )


def check_t4(rel, context, quote, evidence_type):
    subset(
        rel,
        {"direction", "direction_cue", "unit", "classes", "weight_scale"}
        | PARAMETERS
        | WEIGHTS,
        "T4 relationship",
    )
    choice(
        rel.get("direction"),
        {"increasing", "decreasing", "optimum_range", "non_monotonic", "unclear"},
        "T4 direction",
    )
    if (
        "direction_cue" in rel
        and nonempty(rel["direction_cue"], "direction_cue") not in quote
    ):
        raise ValueError("Direction cue must occur in quote")
    groups = {
        name: fields & rel.keys()
        for name, fields in (
            ("parameters", PARAMETERS),
            ("classes", {"classes"}),
            ("weight", WEIGHTS),
        )
    }
    proofs = context.get("source_check", {})
    subset(
        proofs,
        {name for name, fields in groups.items() if fields},
        "context.source_check",
    )
    for name, fields in groups.items():
        if not fields:
            continue
        cue = nonempty(proofs.get(name), f"context.source_check.{name}")
        if cue not in quote:
            raise ValueError(f"{name} basis must be verbatim in the located quote")
        nonempty(context.get("calibration_hold"), "calibration_hold")
        for field in fields:
            ground(rel[field], numbers(cue), field)
    if groups["parameters"]:
        if evidence_type not in {"literature_relationship", "expert"}:
            raise ValueError("Selection-only evidence cannot carry shape parameters")
        cue = proofs["parameters"]
        if re.search(
            r"\b(?:observed|used in areas|found in areas|study sites)\b", cue, re.I
        ) and not re.search(
            r"\b(?:required|minimum|maximum|limit|threshold|unsuitable|optimum|excluded)\b",
            cue,
            re.I,
        ):
            raise ValueError(
                "Observed-use excerpt cannot establish a source-defined limit"
            )
        nonempty(rel.get("unit"), "source parameter unit")
        for key in groups["parameters"]:
            numeric(rel[key], key)
        present = [
            rel[key]
            for key in ("abs_min", "opt_low", "opt_high", "abs_max")
            if key in rel
        ]
        if present != sorted(present):
            raise ValueError("Source parameter endpoints out of order")
    if groups["classes"]:
        rows = rel["classes"]
        if not isinstance(rows, list) or not rows:
            raise ValueError("Expected source class rows")
        for row in rows:
            subset(row, {"range", "label", "rank", "score"}, "source class row")
            for key in ("range", "label"):
                literal = nonempty(row.get(key), f"class {key}")
                if literal not in proofs["classes"]:
                    raise ValueError(f"Source class {key} must occur in class excerpt")
            for key in row.keys() & {"rank", "score"}:
                numeric(row[key], key)
    if groups["weight"]:
        for key in groups["weight"]:
            numeric(rel[key], key)
        if "weight" in rel:
            nonempty(rel.get("weight_scale"), "source weight_scale")
        if "ahp_weight_pct" in rel:
            percent_anchor(rel["ahp_weight_pct"], proofs["weight"])
    elif "weight_scale" in rel:
        raise ValueError("Weight scale without source weight")
    if "reported_values" in context:
        nonempty(context.get("calibration_hold"), "calibration_hold")


def build_unit(draft, scope, source_id, quote, page):
    """Return a CIAT staging dict; the caller supplies the actual page text slice."""
    subset(
        draft,
        set(SCOPE_FIELDS)
        | CHOICES.keys()
        | TEXT_FIELDS
        | {"evidence_id", "relationship", "context"},
        "draft",
    )
    if not isinstance(scope, dict):
        raise ValueError("Expected a scoped extraction plan")
    lane = {k: identifier(scope.get(k), k) for k in SCOPE_FIELDS}
    choice(lane["use_role"], ROLES, "use_role")
    for key in SCOPE_FIELDS:
        if key in draft and draft[key] != lane[key]:
            raise ValueError(f"{key} disagrees with authorised scope")
    if type(page) is not int or page < 1:
        raise ValueError("Expected one-based PDF page")
    nonempty(quote, "quote")
    if sum(c.isalnum() for c in quote) < 12:
        raise ValueError("Quote too short to anchor the claim")
    for field, choices in CHOICES.items():
        choice(draft.get(field), choices, field)
    for key in draft.keys() & TEXT_FIELDS:
        nonempty(draft[key], key)
    if (draft["claim_scope"] != "practice_technology") != bool(draft.get("taxon")):
        raise ValueError(
            "Species/crop claims require a taxon; practice claims cannot carry one"
        )
    if draft["claim_basis"] == "cited_secondary" and not (
        draft.get("attribution") or draft.get("lineage_of")
    ):
        raise ValueError("Record the cited primary attribution or lineage")
    context = draft.get("context")
    if not isinstance(context, dict):
        raise ValueError("Expected context with practice_as_described")
    json.dumps(context, allow_nan=False)
    nonempty(context.get("practice_as_described"), "practice_as_described")
    rel = draft.get("relationship")
    if not isinstance(rel, dict) or not rel:
        raise ValueError("Supply a relationship object")
    role = lane["use_role"]
    subset(
        context,
        COMMON_CONTEXT
        | (
            T4_CONTEXT
            if role in {"structural_suitability", "operational_risk"}
            else set()
        ),
        "context",
    )
    if "component_share_pct" in context:
        numeric(context["component_share_pct"], "component_share_pct")
        percent_anchor(context["component_share_pct"], quote)
    if "model_use" in context:
        subset(
            context["model_use"],
            {"verified", "method", "criterion", "note"},
            "context.model_use",
        )
        if (
            "verified" in context["model_use"]
            and type(context["model_use"]["verified"]) is not bool
        ):
            raise ValueError("model_use.verified must be a boolean")
    if role in EFFECTS:
        effect_relationship(rel, quote)
        if role == "asset_vulnerability":
            nonempty(context.get("hazard_type"), "hazard_type")
    elif role == "structural_suitability":
        check_t4(rel, context, quote, draft["evidence_type"])
    anchors = numbers(quote)
    ground(rel, anchors, "relationship")
    if "reported_values" in context:
        ground(context["reported_values"], anchors, "context.reported_values")
    return {
        **deepcopy(draft),
        **lane,
        "source_id": identifier(source_id, "source_id"),
        "evidence_id": identifier(draft.get("evidence_id"), "evidence_id"),
        "page": page,
        "quote": quote,
        "locator_type": "page",
        "ruleset_version": RULESET,
        "reviewer_ok": False,
    }
