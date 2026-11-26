"""Human-readable Markdown report for one dataset build (pure)."""
from __future__ import annotations


def _table(header: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def _inspection_section(metadata: dict) -> str:
    inspection = metadata.get("source", {}).get("inspection")
    if not inspection:
        return ""
    conn = inspection["connection"]
    lines = [
        "## Source inspection",
        "",
        f"- Database connection: {conn['status']} (database `{conn['database']}`, "
        f"server {conn['server_version']})",
        f"- Calendar price: {inspection['calendar_price']['note']}",
        "",
        _table(
            ["table", "columns"],
            [[t, ", ".join(cols)] for t, cols in inspection["tables"].items()],
        ),
        "",
        _table(
            ["measure", "count"],
            [[k, v] for k, v in {**inspection["row_counts"], **inspection["null_counts"]}.items()],
        ),
    ]
    return "\n".join(lines)


def render_markdown(metadata: dict, validation: dict) -> str:
    cutoff = metadata["cutoff"]
    positive = next(
        (d["percentage"] for d in validation["label_distribution"] if d["high_demand_proxy"] == 1),
        None,
    )
    counts = metadata["row_counts"]
    sections = [
        f"# Feature dataset {metadata['dataset_version']}",
        "\n".join(
            [
                f"- Cutoff: **{cutoff['cutoff_date']}** ({cutoff['selection_rule']}): "
                f"{cutoff['selection_reason']}",
                f"- History window: {cutoff['history_start_date']} to {cutoff['cutoff_date']}; "
                f"label window: after {cutoff['cutoff_date']} up to {cutoff['label_end_date']}",
                f"- Valid cutoff range in the data: {cutoff['earliest_valid_cutoff']} to "
                f"{cutoff['latest_valid_cutoff']}",
                f"- Rows: {validation['n_rows']}; positive rate: {positive}",
                f"- Validation: {'passed' if validation['passed'] else 'FAILED'}",
            ]
        ),
        "## Target\n\n" + metadata["target_definition"],
        _inspection_section(metadata),
        "## Row counts and missing-value rules applied\n\n"
        + _table(["step", "rows"], [[k, v] for k, v in counts.items()]),
        "## Validation checks\n\n"
        + _table(
            ["check", "result"],
            [[k, "pass" if v else "FAIL"] for k, v in validation["checks"].items()],
        ),
        "## Label distribution\n\n"
        + _table(
            ["high_demand_proxy", "count", "percentage"],
            [[d["high_demand_proxy"], d["count"], d["percentage"]]
             for d in validation["label_distribution"]],
        ),
        "## Limitations\n\n" + "\n".join(f"- {text}" for text in metadata["limitations"]),
    ]
    if validation["warnings"]:
        sections.append("## Warnings\n\n" + "\n".join(f"- {w}" for w in validation["warnings"]))
    files = [[f["name"], f["bytes"], f["sha256"]] for f in metadata["files"].values() if f]
    sections.append("## Files\n\n" + _table(["file", "bytes", "sha256"], files))
    return "\n\n".join(part for part in sections if part) + "\n"
