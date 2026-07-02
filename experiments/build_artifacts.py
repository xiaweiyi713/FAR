"""Build the two required tables and three required figures from recorded reports only."""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
from pathlib import Path
from typing import Any

from bench.build.common import read_jsonl, sha256_file, write_json


def _mapping(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("inputs must use LABEL=/path/to/file")
        label, raw_path = value.split("=", 1)
        result[label] = Path(raw_path)
    return result


def _validated_reports(paths: dict[str, Path]) -> dict[str, dict[str, Any]]:
    reports = {}
    for label, path in paths.items():
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("schema_version") != "falsirag-evaluation-report-v1":
            raise ValueError(f"{path}: unsupported report schema")
        scores_path = path.parent / "scores.jsonl"
        if report.get("provenance", {}).get("scores_sha256") != sha256_file(scores_path):
            raise ValueError(f"{path}: scores fingerprint mismatch")
        reports[label] = report
    return reports


def _report_publication_summary(report: dict[str, Any]) -> dict[str, Any]:
    publication = report.get("publication", {})
    if not isinstance(publication, dict):
        publication = {}
    scored_splits = publication.get("scored_splits", [])
    if not isinstance(scored_splits, list):
        scored_splits = []
    return {
        "publication_ready": bool(report.get("publication_ready")),
        "partial": bool(report.get("partial")),
        "phase": publication.get("phase"),
        "scored_splits": sorted(map(str, scored_splits)),
    }


def _validate_artifact_publication_scope(
    reports: dict[str, dict[str, Any]],
    *,
    require_publication_ready: bool,
    require_test_only: bool,
) -> dict[str, dict[str, Any]]:
    summary = {
        label: _report_publication_summary(report) for label, report in sorted(reports.items())
    }
    if require_publication_ready:
        not_ready = [
            label
            for label, item in summary.items()
            if item["partial"] or not item["publication_ready"]
        ]
        if not_ready:
            raise ValueError(f"publication artifacts require ready reports: {not_ready}")
    if require_test_only:
        non_test = [
            label
            for label, item in summary.items()
            if item["phase"] != "test" or set(item["scored_splits"]) != {"test"}
        ]
        if non_test:
            raise ValueError(f"publication artifacts require test-only reports: {non_test}")
    return summary


def _table_rows(reports: dict[str, dict[str, Any]], labels: list[str]) -> list[dict[str, Any]]:
    rows = []
    for label in labels:
        report = reports[label]
        metrics = report["aggregate"]["metrics"]
        row: dict[str, Any] = {"method": label, "samples": report["samples"]}
        for metric in (
            "answer_correctness",
            "typed_conflict_f1",
            "revision_accuracy",
            "overclaim_reduction",
            "counter_evidence_recall",
            "unsupported_claim_rate",
        ):
            row[metric] = metrics.get(metric, 0.0)
            interval = report.get("confidence_intervals", {}).get(metric)
            row[f"{metric}_ci"] = (
                f"[{interval['lower']:.4f}, {interval['upper']:.4f}]" if interval else "n/a"
            )
        rows.append(row)
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_latex(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        r"\begin{tabular}{lrrrr}",
        r"\toprule",
        r"Method & Answer & Typed F1 & Revision & Counter Recall \\",
        r"\midrule",
    ]
    for row in rows:
        method = str(row["method"]).replace("_", "\\_")
        lines.append(
            f"{method} & {row['answer_correctness']:.3f} & "
            f"{row['typed_conflict_f1']:.3f} & {row['revision_accuracy']:.3f} & "
            f"{row['counter_evidence_recall']:.3f} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_plotting_backend() -> tuple[Any, Any]:
    try:
        return (
            importlib.import_module("matplotlib.pyplot"),
            importlib.import_module("matplotlib.font_manager"),
        )
    except ImportError as exc:
        raise RuntimeError(
            "Building FAR tables and figures requires the optional eval dependencies. "
            "Install them with `uv sync --extra eval` for local development or "
            "`pip install 'falsification-augmented-retrieval[eval]'` from a package."
        ) from exc


def _configure_unicode_font(plt: Any, font_manager: Any) -> Path | None:
    """Select a CJK-capable font reproducibly across Mac, WSL, and Linux."""

    configured = os.environ.get("FAR_UNICODE_FONT")
    candidates = [Path(configured).expanduser()] if configured else []
    candidates.extend(
        [
            Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
            Path("/mnt/c/Windows/Fonts/msyh.ttc"),
            Path("/mnt/c/Windows/Fonts/simhei.ttf"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"),
        ]
    )
    for font_path in candidates:
        if not font_path.is_file():
            continue
        try:
            font_manager.fontManager.addfont(font_path)
            family = font_manager.FontProperties(fname=font_path).get_name()
        except (OSError, RuntimeError, ValueError):
            continue
        plt.rcParams["font.family"] = family
        return font_path
    return None


def build(
    report_paths: dict[str, Path],
    prediction_paths: dict[str, Path],
    output_dir: Path,
    *,
    require_publication_ready: bool = False,
    require_test_only: bool = False,
) -> dict[str, Any]:
    reports = _validated_reports(report_paths)
    publication_summary = _validate_artifact_publication_scope(
        reports,
        require_publication_ready=require_publication_ready,
        require_test_only=require_test_only,
    )
    plt, font_manager = _load_plotting_backend()
    unicode_font = _configure_unicode_font(plt, font_manager)

    output_dir.mkdir(parents=True, exist_ok=True)
    main_labels = [label for label in reports if "minus_" not in label]
    ablation_labels = [label for label in reports if label == "far" or "minus_" in label]
    if not main_labels or len(ablation_labels) < 2:
        raise ValueError("artifact build requires main methods and FAR plus at least one ablation")
    main_rows = _table_rows(reports, main_labels)
    ablation_rows = _table_rows(reports, ablation_labels)
    _write_csv(output_dir / "main_results.csv", main_rows)
    _write_csv(output_dir / "ablation_results.csv", ablation_rows)
    _write_latex(output_dir / "main_results.tex", main_rows)
    _write_latex(output_dir / "ablation_results.tex", ablation_rows)

    categories = sorted(next(iter(reports.values()))["aggregate"]["by_category"])
    x = list(range(len(categories)))
    width = 0.8 / len(main_labels)
    fig, axis = plt.subplots(figsize=(10, 4.8))
    for index, label in enumerate(main_labels):
        values = [
            reports[label]["aggregate"]["by_category"][category]["revision_accuracy"]
            for category in categories
        ]
        offset = (index - (len(main_labels) - 1) / 2) * width
        axis.bar([position + offset for position in x], values, width, label=label)
    axis.set_xticks(x, [item.replace("_", "\n") for item in categories])
    axis.set_ylabel("Revision accuracy")
    axis.set_ylim(0, 1)
    axis.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(output_dir / "typed_conflict_breakdown.png", dpi=200)
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(8, 4.5))
    recall = [
        reports[label]["aggregate"]["metrics"]["counter_evidence_recall"] for label in main_labels
    ]
    axis.bar(main_labels, recall)
    axis.set_ylabel("Counter-evidence recall")
    axis.set_ylim(0, 1)
    axis.tick_params(axis="x", rotation=25)
    fig.tight_layout()
    fig.savefig(output_dir / "counter_evidence_recall.png", dpi=200)
    plt.close(fig)

    far_predictions_path = prediction_paths.get("far")
    if far_predictions_path is None:
        raise ValueError("revision trace figure requires --prediction far=/path/predictions.jsonl")
    predictions = read_jsonl(far_predictions_path)
    selected = next(
        (
            row
            for row in predictions
            if any(
                trace.get("changed") for trace in row.get("metadata", {}).get("revision_trace", [])
            )
        ),
        None,
    )
    if selected is None:
        raise ValueError("recorded FAR predictions contain no changed revision trace")
    trace = next(item for item in selected["metadata"]["revision_trace"] if item.get("changed"))
    fig, axis = plt.subplots(figsize=(11, 4.5))
    axis.axis("off")
    text = (
        f"Sample {selected['sample_id']} — {trace['action']}\n\n"
        f"BEFORE\n{trace['before']}\n\nAFTER\n{trace['after']}\n\n"
        f"CONFLICT\n{', '.join(trace['conflict_types'])}\n{trace['rationale']}"
    )
    axis.text(0.02, 0.98, text, va="top", wrap=True, fontsize=10)
    fig.tight_layout()
    fig.savefig(output_dir / "revision_trace_case.png", dpi=200)
    plt.close(fig)

    outputs = (
        sorted(output_dir.glob("*.csv"))
        + sorted(output_dir.glob("*.tex"))
        + sorted(output_dir.glob("*.png"))
    )
    manifest = {
        "schema_version": "far-artifact-manifest-v1",
        "diagnostic_only": any(
            bool(report.get("partial")) or not bool(report.get("publication_ready"))
            for report in reports.values()
        ),
        "publication_ready": all(
            bool(report.get("publication_ready")) for report in reports.values()
        ),
        "test_only": all(
            item["phase"] == "test" and set(item["scored_splits"]) == {"test"}
            for item in publication_summary.values()
        ),
        "phases": sorted(
            {str(item["phase"]) for item in publication_summary.values() if item["phase"]}
        ),
        "scored_splits": sorted(
            {split for item in publication_summary.values() for split in item["scored_splits"]}
        ),
        "strict_requirements": {
            "publication_ready": require_publication_ready,
            "test_only": require_test_only,
        },
        "publication": publication_summary,
        "reports": {label: sha256_file(path) for label, path in report_paths.items()},
        "predictions": {label: sha256_file(path) for label, path in prediction_paths.items()},
        "unicode_font": (
            {"path": str(unicode_font), "sha256": sha256_file(unicode_font)}
            if unicode_font is not None
            else None
        ),
        "outputs": {path.name: sha256_file(path) for path in outputs},
    }
    write_json(output_dir / "artifact_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="append", required=True)
    parser.add_argument("--prediction", action="append", default=[])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--require-publication-ready",
        action="store_true",
        help="fail unless every input report is complete and publication-ready",
    )
    parser.add_argument(
        "--require-test-only",
        action="store_true",
        help="fail unless every input report scores only the externally blind test split",
    )
    args = parser.parse_args()
    manifest = build(
        _mapping(args.report),
        _mapping(args.prediction),
        args.output_dir,
        require_publication_ready=args.require_publication_ready,
        require_test_only=args.require_test_only,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
