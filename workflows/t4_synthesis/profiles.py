"""Typed review-only reference execution; no raster adapter or acceptance writes."""
import bisect
import math
from urllib.parse import urlparse

from synthesis.core import require, nonempty

KINDS = {"composite_scoping", "precomputed_unit_index"}


def number(x):
    return type(x) in {int, float} and math.isfinite(x)


def exact(value, keys, label):
    require(isinstance(value, dict) and set(value) == set(keys.split()), label)


def names(value):
    return isinstance(value, list) and bool(value) and all(nonempty(x) for x in value) and len(value) == len(set(value))


def smooth(kind, x20, x80, value):
    require(kind in {"logistic", "log_logistic"} and number(x20) and number(x80)
            and x20 < x80 and (kind != "log_logistic" or x20 > 0), "Invalid 20/80 anchors")
    lo, hi = (math.log(x20), math.log(x80)) if kind == "log_logistic" else (x20, x80)
    width = hi - lo
    require(number(width) and width > 0, "Curve anchors exceed numeric resolution")
    if value is None:
        return None
    require(number(value), "Finite numeric curve input required")
    if kind == "log_logistic":
        require(value >= 0, "Negative log-logistic input")
        if value == 0:
            return 0.0
        value = math.log(value)
    # Normalize before multiplying: narrow finite anchors must not overflow slope.
    z = 2 * math.log(4) * ((value - lo) / width - 0.5)
    return 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))


def validate_profile(p):
    require(isinstance(p, dict) and p.get("type") in KINDS, "Unknown profile type")
    common = "type unit missing scope inputs"
    extra = ("thermal_season score screens water_policy combined_score_cutoff weight" if p["type"] == "composite_scoping"
             else "score_input area_input area_to_hectares area_policy")
    exact(p, common + " " + extra, "Undeclared or missing profile fields")
    require(p["unit"] == "dimensionless" and p["missing"] is None, "Explicit dimensionless score and null missing required")
    require(isinstance(p["scope"], list) and p["scope"], "Explicit scope required")
    for s in p["scope"]:
        exact(s, "nbs_id family_id subpractice_ids pathways", "Invalid scope fields")
        require(nonempty(s["nbs_id"]) and nonempty(s["family_id"]), "Scope identities required")
        for key in ("subpractice_ids", "pathways"):
            require(names(s[key]) or (s[key] is None and p["type"] == "precomputed_unit_index"), "Explicit scope lists required")
    require(isinstance(p["inputs"], dict) and p["inputs"], "Input definitions required")
    for name, d in p["inputs"].items():
        exact(d, "variable dataset_id unit valid_range", "Invalid input definition")
        require(nonempty(name) and all(nonempty(d[k]) for k in ("variable", "dataset_id", "unit")), "Named quantity and dataset required")
        r = d["valid_range"]
        require(isinstance(r, list) and len(r) == 2 and all(number(x) for x in r) and r[0] < r[1], "Finite input validity range required")
    if p["type"] == "precomputed_unit_index":
        require(p["score_input"] in p["inputs"] and p["area_input"] in p["inputs"]
                and p["score_input"] != p["area_input"] and len(p["inputs"]) == 2, "Exactly two distinct unit inputs required")
        require(p["inputs"][p["score_input"]]["valid_range"] == [0, 1]
                and p["inputs"][p["score_input"]]["unit"] == "dimensionless"
                and p["inputs"][p["score_input"]]["dataset_id"] == p["inputs"][p["area_input"]]["dataset_id"]
                and p["inputs"][p["area_input"]]["unit"] == "km2"
                and p["inputs"][p["area_input"]]["valid_range"][0] == 0
                and number(p["area_to_hectares"]) and p["area_to_hectares"] == 100
                and p["area_policy"] == "whole_units_partial_bounds_no_prorating", "Native scale and source-area semantics required")
        return
    require(p["water_policy"] == "conditional_unscored" and p["combined_score_cutoff"] is None and p["weight"] is None,
            "No inferred scalar cutoff or weight; conditional water remains unscored")
    t = p["thermal_season"]
    raw = set(p["inputs"])
    if t is not None:
        exact(t, "kind input mean_output days_output month_lengths threshold operator empty_season_score", "Invalid thermal derivation")
        require(t["kind"] == "periodic_monthly_temperature_season" and t["operator"] == "ge"
                and number(t["threshold"]) and type(t["empty_season_score"]) in {int, float} and t["empty_season_score"] == 0,
                "Explicit thermal-only threshold and empty-season score required")
        require(t["month_lengths"] == [31,28,31,30,31,30,31,31,30,31,30,31]
                and all(type(x) is int for x in t["month_lengths"]), "No-leap calendar required")
        ids = [t[k] for k in ("input", "mean_output", "days_output")]
        require(len(set(ids)) == 3 and set(ids) <= raw, "Thermal inputs/outputs must be separately declared")
        require(p["inputs"][t["input"]]["unit"] == p["inputs"][t["mean_output"]]["unit"] == "degC"
                and p["inputs"][t["days_output"]]["unit"] == "days", "Thermal units differ")
        raw -= {t["mean_output"], t["days_output"]}
    used = set()
    def node(n, depth=0):
        require(depth <= 8 and isinstance(n, dict), "Bounded typed score tree required")
        if n.get("kind") == "minimum":
            exact(n, "kind children", "Invalid minimum node")
            require(isinstance(n["children"], list) and 2 <= len(n["children"]) <= 16, "Minimum needs 2-16 children")
            for child in n["children"]:
                node(child, depth + 1)
        else:
            exact(n, "kind input x20 x80", "Invalid curve node")
            require(n["input"] in p["inputs"] and (t is None or n["input"] != t["input"]), "Curve input must be scalar")
            smooth(n["kind"], n["x20"], n["x80"], None)
            r = p["inputs"][n["input"]]["valid_range"]
            require(r[0] <= n["x20"] < n["x80"] <= r[1], "Anchors outside input validity domain")
            used.add(n["input"])
    node(p["score"])
    require(isinstance(p["screens"], list), "Explicit named screens required")
    screen_ids = set()
    for s in p["screens"]:
        exact(s, "id input operator threshold water_bypass", "Invalid screen")
        require(nonempty(s["id"]) and s["id"] not in screen_ids and s["input"] in used
                and s["operator"] in {"lt", "le", "gt", "ge"} and number(s["threshold"])
                and type(s["water_bypass"]) is bool, "Invalid named component screen")
        screen_ids.add(s["id"])
        if t and s["input"] in {t["mean_output"], t["days_output"]}:
            require(not s["water_bypass"], "Water cannot bypass a thermal screen")
    require(set(p["inputs"]) == used | ({t["input"]} if t else set()), "Unused or unresolved profile input")


def monthly_to_daily(monthly, lengths):
    if monthly is None or any(v is None for v in monthly):
        return None
    require(isinstance(monthly, list) and len(monthly) == 12 and all(number(x) for x in monthly), "Twelve finite monthly values required")
    centres, start = [], 0
    for length in lengths:
        centres.append(start + (length + 1) / 2)
        start += length
    xp, yp = [centres[-1]-365] + centres + [centres[0]+365], [monthly[-1]] + monthly + [monthly[0]]
    out = []
    for day in range(1, 366):
        i = bisect.bisect_right(xp, day) - 1
        out.append(yp[i] + (yp[i+1]-yp[i]) * (day-xp[i]) / (xp[i+1]-xp[i]))
    return out


def _scope(p, c):
    return any(c.get("nbs_id") == s["nbs_id"] and c.get("family_id") == s["family_id"]
               and (s["subpractice_ids"] is None or c.get("subpractice_id") in s["subpractice_ids"])
               and (s["pathways"] is None or c.get("pathway") in s["pathways"]) for s in p["scope"])


def _value(p, key, value):
    if value is not None:
        lo, hi = p["inputs"][key]["valid_range"]
        require(number(value) and lo <= value <= hi, "Invalid numeric input: " + key)
    return value


def evaluate_profile(p, values, context):
    validate_profile(p)
    require(isinstance(values, dict) and isinstance(context, dict), "Object inputs and context required")
    require(set(values) <= set(p["inputs"]), "Undeclared input")
    out = dict(state="outside_review_scope", score=None, screen_reasons=[], area_ha=None,
               area_lower_ha=None, area_upper_ha=None, runtime_implemented=False)
    if not _scope(p, context):
        return out
    host, legal = context.get("host_state", "unknown"), context.get("legal_state", "unknown")
    require(host in {"present", "absent", "unknown"} and legal in {"clear", "excluded", "unknown"}, "Invalid host/legal state")
    if p["type"] == "precomputed_unit_index":
        require(nonempty(context.get("unit_id")) and context.get("spatial_relation") in {"whole", "partial"}
                and (context.get("geometry_valid") is None or type(context.get("geometry_valid")) is bool), "Unit identity, overlay relation and geometry QA required")
        gate = "excluded_existing_gate" if legal == "excluded" or host == "absent" else None
        if context.get("geometry_valid") is None:
            out["state"] = gate or "unknown_geometry"
            out["data_state"] = "unknown_geometry"
            return out
        if not context["geometry_valid"]:
            out["state"] = gate or "invalid_geometry"
            out["data_state"] = "invalid_geometry"
            return out
        v, area = (_value(p, k, values.get(k)) for k in (p["score_input"], p["area_input"]))
        if v is None or area is None:
            out["state"] = gate or "unknown"
            out["data_state"] = "unknown"
            return out
        require((v == 0) == (area == 0), "Zero score/area mismatch")
        if area == 0:
            out.update(state=gate or "no_modelled_restorable_area", data_state="no_modelled_restorable_area", area_ha=0, area_lower_ha=0, area_upper_ha=0)
            return out
        total = area * p["area_to_hectares"]
        require(number(total), "Source area conversion overflow")
        out["score"] = v
        if legal == "excluded" or host == "absent":
            out["state"] = "excluded_existing_gate"
        elif legal == "unknown" or host == "unknown":
            out["state"] = "existing_gate_unresolved"
        else:
            out.update(state="candidate_whole_unit" if context["spatial_relation"] == "whole" else "partial_unit_allocation_unresolved",
                       area_ha=total if context["spatial_relation"] == "whole" else None,
                       area_lower_ha=total if context["spatial_relation"] == "whole" else 0,
                       area_upper_ha=total)
        return out
    water = context.get("water_context", "unknown")
    require(water in {"ordinary_rainfed", "mapped_potential_refuge", "unknown"}, "Invalid water context")
    if water == "mapped_potential_refuge":
        require(nonempty(context.get("water_evidence_ref")), "Mapped refuge needs evidence reference")
    t, data, empty = p["thermal_season"], {}, set()
    if t:
        require(not ({t["mean_output"], t["days_output"]} & set(values)), "Derived thermal inputs cannot be supplied or substituted")
    for key in p["inputs"]:
        if t and key in {t["mean_output"], t["days_output"]}:
            continue
        value = values.get(key)
        if t and key == t["input"]:
            require(value is None or (isinstance(value, list) and len(value) == 12), "Twelve monthly temperatures required")
            if value is not None:
                for v in value:
                    _value(p, key, v)
            daily = monthly_to_daily(value, t["month_lengths"])
            warm = None if daily is None else [x for x in daily if x >= t["threshold"]]
            data[t["mean_output"]] = None if not warm else sum(warm) / len(warm)
            data[t["days_output"]] = None if warm is None else len(warm)
            if warm == []:
                empty.add(t["mean_output"])
            for name in (t["mean_output"], t["days_output"]):
                _value(p, name, data[name])
        else:
            data[key] = _value(p, key, value)
    def evaluate(n):
        if n["kind"] == "minimum":
            scores = [evaluate(child) for child in n["children"]]
            return None if None in scores else min(scores)
        return t["empty_season_score"] if n["input"] in empty else smooth(n["kind"], n["x20"], n["x80"], data[n["input"]])
    out["score"] = evaluate(p["score"])
    out["derived"] = {k: data[k] for k in (t["mean_output"], t["days_output"])} if t else {}
    failures = []
    for screen in p["screens"]:
        x, limit = data[screen["input"]], screen["threshold"]
        if x is not None and {"lt": x < limit, "le": x <= limit, "gt": x > limit, "ge": x >= limit}[screen["operator"]]:
            failures.append(screen)
    out["screen_reasons"] = [s["id"] for s in failures]
    if legal == "excluded" or host == "absent":
        state = "excluded_existing_gate"
    elif any(not s["water_bypass"] for s in failures):
        state = "outside_default_component_screen"
    elif water == "mapped_potential_refuge":
        state = "conditional_water_pathway_unscored"
    elif failures:
        state = "outside_default_rainfed_opportunity"
    elif out["score"] is None:
        state = "unknown_climate"
    elif host == "unknown" or legal == "unknown":
        state = "climate_pass_host_or_legal_unresolved"
    elif water == "unknown":
        state = "climate_pass_water_context_unresolved"
    else:
        state = "candidate_default_rainfed_opportunity"
    if water == "mapped_potential_refuge":
        out["score"] = None
    out["state"] = state
    return out


def evaluate_units(p, records):
    """Call after unioning AOIs. Duplicate units fail, never sum twice."""
    require(p.get("type") == "precomputed_unit_index" and isinstance(records, list), "Unit-index records required")
    ids = [r.get("context", {}).get("unit_id") for r in records]
    require(len(ids) == len(set(ids)) and all(nonempty(x) for x in ids), "Duplicate or absent unit identity")
    return [evaluate_profile(p, r["values"], r["context"]) for r in records]


def validate_candidate(record):
    exact(record, "format id status activate profile justification evidence_refs", "Invalid pending candidate fields")
    require(record["format"] == "ruralscan.t4-profile-candidate.v1" and nonempty(record["id"])
            and record["status"] == "pending" and record["activate"] is False
            and isinstance(record["evidence_refs"], list) and record["evidence_refs"], "Pending candidate provenance required")
    exact(record["justification"], "rationale mechanism source_relationship analyst_choices transfer_limits binding area_accounting replacement_policy approval_remaining", "Separate candidate scientific rationales required")
    require(all(nonempty(x) for x in record["justification"].values()), "Empty candidate rationale")
    for ref in record["evidence_refs"]:
        exact(ref, "source_id citation url locator claim_role admission_status", "Invalid candidate source reference")
        require(all(nonempty(x) for x in ref.values()), "Source reference fields required")
        parsed = urlparse(ref["url"])
        require(parsed.scheme in {"http", "https"} and bool(parsed.netloc), "Public source URL required")
    validate_profile(record["profile"])
    return record


def evaluate_candidate(record, values, context):
    validate_candidate(record)
    return evaluate_profile(record["profile"], values, context)


def validate_definitions(p, definitions, practice, family, applicability):
    """Official mappings additionally require adopted quantities and preferred bindings."""
    validate_profile(p)
    fam = [r for r in definitions["schema/registers/FAM_family_registry.csv"]
           if r["nbs_id"] == practice and r["suitability_family_id"] == family]
    for s in p["scope"]:
        require(s["nbs_id"] == practice and s["family_id"] == family, "Profile outside official proposal family")
        if s["subpractice_ids"] is not None:
            require(set(s["subpractice_ids"]) <= {r.get("subpractice_id") for r in fam}, "Unregistered profile subpractice")
    variables = {r["canonical_variable_id"]: r for r in definitions["schema/registers/VONT_variable_ontology.csv"]}
    datasets = {r["dataset_id"] for r in definitions["schema/T1_data_registry.csv"]}
    for d in p["inputs"].values():
        require(d["variable"] in variables and d["dataset_id"] in datasets, "Unadopted profile quantity or dataset")
        require(variables[d["variable"]]["canonical_unit"] == d["unit"], "Profile input unit differs from canonical quantity")
        eligible = [b for b in definitions["schema/registers/BIND_dataset_binding.csv"]
                    if b["variable"] == d["variable"] and (b.get("scope_type") == "global"
                    or (b.get("scope_type"), b.get("scope_id")) == (applicability["scope_type"], applicability["scope_id"]))]
        exact_context = [b for b in eligible if (b.get("scope_type"), b.get("scope_id"))
                         == (applicability["scope_type"], applicability["scope_id"])]
        choices = exact_context or eligible
        require(choices, "No pinned profile input binding")
        rank = min(int(b["preference_rank"]) for b in choices)
        require(any(b["dataset_id"] == d["dataset_id"] and int(b["preference_rank"]) == rank
                    and b.get("status") in {"catalogued", "community"} for b in choices), "No usable preferred profile binding")


def same(actual, expected):
    if number(actual) and number(expected):
        return math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9)
    if isinstance(actual, dict) and isinstance(expected, dict):
        return set(actual) == set(expected) and all(same(actual[k], expected[k]) for k in actual)
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(same(a, b) for a, b in zip(actual, expected))
    return type(actual) is type(expected) and actual == expected


def boundary_cases(row):
    p = row["relationship_params"]
    validate_profile(p)
    require(p["type"] == row["relationship_type"] and row["weight_default"] is None,
            "Profile type mismatch or inferred criterion weight")
    cases = row["justification"].get("boundary_cases")
    require(isinstance(cases, list) and cases, "Structured boundary examples required")
    states, reasons, scored, empty_season = set(), set(), False, False
    for case in cases:
        exact(case, "input expected reason", "Invalid profile boundary case")
        exact(case["input"], "values context", "Boundary input needs values and context")
        require(nonempty(case["reason"]), "Boundary rationale required")
        actual = evaluate_profile(p, case["input"]["values"], case["input"]["context"])
        require(same(actual, case["expected"]), "Boundary example disagrees with profile")
        states.add(actual["state"])
        reasons.update(actual["screen_reasons"])
        scored = scored or number(actual["score"])
        t = p.get("thermal_season")
        if t and actual.get("derived", {}).get(t["days_output"]) == 0:
            empty_season = True
    require("outside_review_scope" in states and any(s.startswith("unknown") for s in states),
            "Check missing and outside-scope profile states explicitly")

    require(scored and "excluded_existing_gate" in states, "Check scored case and known independent exclusion")
    if p["type"] == "precomputed_unit_index":
        require({"candidate_whole_unit", "partial_unit_allocation_unresolved", "no_modelled_restorable_area"} <= states,
                "Check whole, partial and zero-area unit semantics")
    else:
        require({s["id"] for s in p["screens"]} <= reasons and "conditional_water_pathway_unscored" in states,
                "Check all component screens and conditional water state")
        require(p["thermal_season"] is None or empty_season, "Check known empty thermal season")
