"""Render a read-only index of candidate rows from a verified release."""

import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from git_snapshot import require

# Display only structured classifications. Full notes and source extracts stay
# in the pinned analytical record, accessible through each row's source link.
TABLES = {
    "T3": (
        "Hazard responses",
        (
            "Hazard",
            "Risk role",
            "Farming system",
            "Scope",
            "Potential or sensitivity",
            "Confidence",
        ),
    ),
    "T4": (
        "Suitability mappings",
        (
            "Variable",
            "Family",
            "Function role",
            "Function options",
            "Function selected",
            "Spatially validated",
        ),
    ),
    "T6": (
        "Scorecard effects",
        ("Indicator", "Scope", "Effect direction", "Confidence"),
    ),
    "T6E": (
        "Economic profiles",
        ("Indicator", "Scope", "Numerical range reported", "Confidence"),
    ),
}
EXPLANATIONS = {
    "T3": "For livelihood rows, the rating describes mitigation potential. For investment-risk rows, it describes the asset’s sensitivity to the hazard.",
    "T4": "A selected function still needs checks against the intended spatial inputs and location.",
    "T6": "Use the linked record for the evidence, applicability and caveats behind each effect.",
    "T6E": "Where a numerical range is reported, consult the linked record for its values, units and source conditions.",
}
SOURCE = "https://github.com/CIAT/nbs_ruralscan"
DISPLAY_NAMES = {
    "aez": "Agroecological zone",
    "lic_lmic": "Low and lower-middle income",
    "ndvi": "NDVI",
    "soil_ph": "Soil pH",
    "water_harvesting_conservation": "Water harvesting and conservation",
    "livelihood_mitigation": "Livelihood risk mitigation",
    "asset_threat": "Threat to the investment",
}


def label(token):
    if token is None:
        return "Unspecified"
    require(
        isinstance(token, str) and re.fullmatch(r"[a-z0-9_-]+", token),
        "Unexpected classification code",
    )
    return DISPLAY_NAMES.get(token, token.replace("_", " ").capitalize())


def scope(row):
    family = row.get("suitability_family_id")
    parts = [label(family.split("__")[-1]) if family else "Practice"]
    kind, value = row.get("scope_type"), row.get("scope_id")
    require(bool(kind) == bool(value), "Incomplete context scope")
    if kind:
        parts.append(f"{label(kind)} · {label(value)}")
    return " / ".join(parts)


def table_lines(release, practice, table, filename, revision, readiness):
    title, headings = TABLES[table]
    rows = release.table(practice, table)
    lines = [f"## {table} {title}", ""]
    if not rows:
        return lines + ["No compiled rows in this release.", ""]
    lines += [
        EXPLANATIONS[table],
        "",
        "| " + " | ".join(headings) + " |",
        "|" + "---|" * len(headings),
    ]
    key = "mapping_id" if table == "T4" else "record_id"
    # Pin the same audited JSON bytes as the release and link to the exact ID
    # line. Fail closed if a later producer changes its serialisation.
    source = release.read_bytes(f"tables/{practice}/{filename}").decode("utf-8")
    field = re.compile(rf'^    "{key}": "([a-z0-9_-]+)",?$')
    locations = {
        match[1]: number
        for number, line in enumerate(source.splitlines(), 1)
        if (match := field.fullmatch(line))
    }
    ids = [row[key] for row in rows]
    require(
        len(ids) == len(set(ids)) and set(ids) == locations.keys(),
        f"Cannot locate all original {table} records",
    )
    url = f"{SOURCE}/blob/{revision}/schema/recipes/{practice}/{filename}"
    for row in rows:
        identifier = row[key]
        if table == "T4":
            entry = readiness[identifier]
            family = scope(row)
            crop = row.get("relationship_params", {}).get("host_crop")
            if crop:
                family += f" / Host crop · {label(crop)}"
            cells = [
                label(row["variable"]),
                family,
                label(entry["role"]),
                str(len(entry["functions"])),
                "Yes" if entry["readiness"]["effective_function_id"] else "No",
                "Yes" if entry["readiness"]["execution_ready"] else "No",
            ]
        elif table == "T3":
            role = row["risk_role"]
            rating = {
                "livelihood_mitigation": "mitigation_potential",
                "asset_threat": "asset_sensitivity",
            }[role]
            cells = [
                label(row["hazard_type"]),
                label(role),
                label(row["farming_system"]),
                scope(row),
                label(row.get(rating)),
                label(row.get("confidence")),
            ]
        else:
            result = (
                label(row.get("effect_direction"))
                if table == "T6"
                else ("Yes" if row.get("economic_value_range") else "No")
            )
            cells = [
                label(row["variable_id"]),
                scope(row),
                result,
                label(row.get("effect_confidence")),
            ]
        cells[0] = f'[{cells[0]}]({url}#L{locations[identifier]} "{identifier}")'
        lines.append("| " + " | ".join(cells) + " |")
    return lines + [""]


def render_index(release, summary, stems):
    revision = summary["source_revision"]
    release_id = summary["release_id"]
    pin = f"Candidate release `{release_id}` · [source revision]({SOURCE}/tree/{revision})."
    overview = [
        "# Recipe index",
        "",
        "Choose a practice to inspect its compiled rules and effects. Each entry links to the exact analytical record, including its evidence references and caveats.",
        "",
        pin,
        "",
        "| Practice | T3 · Hazard responses | T4 · Suitability mappings | T6 · Scorecard effects | T6E · Economic profiles |",
        "|---|---:|---:|---:|---:|",
    ]
    files = {}
    for practice in release.practices:
        require(re.fullmatch(r"[a-z0-9_]+", practice), "Unexpected practice ID")
        name = label(practice)
        counts = summary["practices"][practice]
        overview.append(
            f"| [{name}]({practice}.md) | "
            + " | ".join(str(counts[t]) for t in TABLES)
            + " |"
        )
        page = [
            f"# {name}",
            "",
            "[All practices](README.md)",
            "",
            pin,
            "",
            "Jump to "
            + " · ".join(
                f"[{t} {title.lower()}](#{t.lower()}-{title.lower().replace(' ', '-')})"
                for t, (title, _) in TABLES.items()
            )
            + ".",
            "",
        ]
        report = json.loads(release.read_bytes(f"tables/{practice}/T4_readiness.json"))
        readiness = {record["rule_id"]: record for record in report["rows"]}
        for t in TABLES:
            page.extend(
                table_lines(
                    release, practice, t, stems[t] + ".json", revision, readiness
                )
            )
        files[practice + ".md"] = "\n".join(page)
    overview += [
        "| **Total** | " + " | ".join(str(summary["totals"][t]) for t in TABLES) + " |",
        "",
        "Counts are analytical rows. A source may contribute to several rows, and one topic can have separate rows for different families and contexts. Zero means no compiled row in this candidate.",
        "",
        "[Check the release and reproduce the index](../../workflows/recipe_release/README.md) · [Read the recipe cookbook](https://github.com/RuralScan/method/blob/0af0f5599c8c71f38b2be40dbda71278cbadfbbe/handbook/start-here.md)",
        "",
    ]
    files["README.md"] = "\n".join(overview)
    return files


def write_index(directory, files):
    directory = Path(directory).absolute()
    if os.path.lexists(directory):
        raise ValueError(f"Choose a new directory for the index: {directory}")
    with TemporaryDirectory(dir=directory.parent) as tmp:
        stage = Path(tmp) / "index"
        stage.mkdir()
        for name, content in files.items():
            (stage / name).write_text(content, encoding="utf-8")
        stage.rename(directory)
