"""Create a gold-free FalsiRAG test bundle for an external custodian."""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from far.bench.build.common import read_jsonl, sha256_file, write_json, write_jsonl
from far.bench.schema import BLIND_TEST_ALLOWED_FIELDS
from far.paths import benchmark_data_dir

DEFAULT_DATA_DIR = benchmark_data_dir()
HANDOFF_SCHEMA_VERSION = "falsirag-blind-custodian-handoff-v1"
FORBIDDEN_BLIND_KEYS = {
    "annotation",
    "annotation_rationale",
    "annotation_status",
    "conflict_type",
    "counter_evidence",
    "depends_on",
    "dependency_group",
    "expected_behavior",
    "expected_conflicts",
    "expected_revision",
    "gold_annotation",
    "gold_evidence",
    "ground_truth_answer",
    "ground_truth_claims",
    "refutes_claim",
    "source_doc_id",
    "source_metadata",
    "supports_claim",
}


def build(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    if data_dir.resolve() == output_dir.resolve():
        raise ValueError("blind bundle output must differ from the source data directory")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("blind bundle output directory must be empty")

    corpus_path = data_dir / "corpus.jsonl"
    test_input_path = data_dir / "splits" / "test_inputs.jsonl"
    test_rows = read_jsonl(test_input_path)
    if not test_rows:
        raise ValueError("blind test input file must not be empty")
    if any(set(row) != BLIND_TEST_ALLOWED_FIELDS for row in test_rows):
        raise ValueError("test_inputs contains fields outside the blind operational schema")
    if any(row.get("split") != "test" for row in test_rows):
        raise ValueError("test_inputs contains a non-test row")
    ids = [str(row["id"]) for row in test_rows]
    if len(set(ids)) != len(ids):
        raise ValueError("test_inputs contains duplicate IDs")

    corpus_rows = read_jsonl(corpus_path)
    public_corpus_fields = (
        "doc_id",
        "title",
        "content",
        "source",
        "date",
        "author",
        "url",
        "license",
        "entities",
    )
    blind_corpus = [
        {field: row[field] for field in public_corpus_fields if field in row} for row in corpus_rows
    ]

    (output_dir / "splits").mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "corpus.jsonl", blind_corpus)
    write_jsonl(output_dir / "splits" / "test_inputs.jsonl", test_rows)
    manifest = {
        "schema_version": "falsirag-blind-bundle-v1",
        "gold_included": False,
        "allowed_test_fields": sorted(BLIND_TEST_ALLOWED_FIELDS),
        "samples": len(test_rows),
        "categories": sorted({str(row["category"]) for row in test_rows}),
        "public_corpus_fields": list(public_corpus_fields),
        "source_corpus_sha256": sha256_file(corpus_path),
        "files": {
            "corpus.jsonl": sha256_file(output_dir / "corpus.jsonl"),
            "splits/test_inputs.jsonl": sha256_file(output_dir / "splits" / "test_inputs.jsonl"),
        },
        "instructions": (
            "Run predictions with --split test --allow-test. Return prediction bundles and "
            "manifests to the trusted scorer; do not request or add gold files here."
        ),
    }
    write_json(output_dir / "blind_bundle_manifest.json", manifest)
    return manifest


def _forbidden_key_paths(value: Any, *, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            if key in FORBIDDEN_BLIND_KEYS:
                paths.append(child_prefix)
            paths.extend(_forbidden_key_paths(child, prefix=child_prefix))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.extend(_forbidden_key_paths(child, prefix=f"{prefix}[{index}]"))
    return paths


def audit_bundle(bundle_dir: Path, *, allow_technical: bool = False) -> dict[str, Any]:
    """Fail closed if a blind bundle is not safe for external handoff."""

    if "technical" in bundle_dir.name.lower() and not allow_technical:
        raise ValueError("technical dry-run bundles cannot be packaged for final handoff")
    expected_files = {
        "blind_bundle_manifest.json",
        "corpus.jsonl",
        "splits/test_inputs.jsonl",
    }
    observed_files = {
        path.relative_to(bundle_dir).as_posix() for path in bundle_dir.rglob("*") if path.is_file()
    }
    if observed_files != expected_files:
        raise ValueError(
            "blind bundle must contain exactly the manifest, corpus, and test_inputs files"
        )
    manifest_path = bundle_dir / "blind_bundle_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "falsirag-blind-bundle-v1":
        raise ValueError("unsupported blind bundle schema")
    if manifest.get("gold_included") is not False:
        raise ValueError("blind bundle manifest reports gold_included=true")
    test_rows = read_jsonl(bundle_dir / "splits" / "test_inputs.jsonl")
    corpus_rows = read_jsonl(bundle_dir / "corpus.jsonl")
    if any(set(row) != BLIND_TEST_ALLOWED_FIELDS for row in test_rows):
        raise ValueError("blind bundle test inputs contain non-operational fields")
    if any(row.get("split") != "test" for row in test_rows):
        raise ValueError("blind bundle contains non-test rows")
    ids = [str(row["id"]) for row in test_rows]
    if len(ids) != len(set(ids)):
        raise ValueError("blind bundle contains duplicate test IDs")
    forbidden: list[str] = []
    for filename, rows in (
        ("blind_bundle_manifest.json", [manifest]),
        ("splits/test_inputs.jsonl", test_rows),
        ("corpus.jsonl", corpus_rows),
    ):
        for row_index, row in enumerate(rows):
            forbidden.extend(f"{filename}:{row_index}:{path}" for path in _forbidden_key_paths(row))
    if forbidden:
        preview = ", ".join(forbidden[:5])
        raise ValueError(f"blind bundle contains forbidden gold/provenance keys: {preview}")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("blind bundle manifest file fingerprints are missing")
    expected_hashes = {
        "corpus.jsonl": sha256_file(bundle_dir / "corpus.jsonl"),
        "splits/test_inputs.jsonl": sha256_file(bundle_dir / "splits" / "test_inputs.jsonl"),
    }
    if files != expected_hashes:
        raise ValueError("blind bundle manifest fingerprints do not match files")
    return {
        "schema_version": "falsirag-blind-bundle-audit-v1",
        "valid": True,
        "bundle_dir": str(bundle_dir),
        "manifest_sha256": sha256_file(manifest_path),
        "samples": len(test_rows),
        "documents": len(corpus_rows),
        "files": {
            "blind_bundle_manifest.json": sha256_file(manifest_path),
            **expected_hashes,
        },
    }


def package_handoff(
    bundle_dir: Path,
    output_dir: Path,
    *,
    config_paths: list[Path],
    frozen_commit: str,
    overwrite: bool = False,
    allow_technical: bool = False,
) -> dict[str, Any]:
    """Build a deterministic ZIP package for an external blind-test custodian."""

    if not frozen_commit.strip():
        raise ValueError("frozen_commit must be non-empty")
    if not config_paths:
        raise ValueError("at least one config file must be included")
    audit = audit_bundle(bundle_dir, allow_technical=allow_technical)
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"{output_dir} exists; pass overwrite=True to replace it")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    bundle_output = output_dir / "blind_bundle"
    (bundle_output / "splits").mkdir(parents=True)
    copied_files = [
        "blind_bundle/blind_bundle_manifest.json",
        "blind_bundle/corpus.jsonl",
        "blind_bundle/splits/test_inputs.jsonl",
    ]
    shutil.copy2(
        bundle_dir / "blind_bundle_manifest.json", bundle_output / "blind_bundle_manifest.json"
    )
    shutil.copy2(bundle_dir / "corpus.jsonl", bundle_output / "corpus.jsonl")
    shutil.copy2(
        bundle_dir / "splits" / "test_inputs.jsonl",
        bundle_output / "splits" / "test_inputs.jsonl",
    )

    config_output = output_dir / "configs"
    config_output.mkdir()
    config_hashes: dict[str, str] = {}
    seen_config_names: set[str] = set()
    for config_path in config_paths:
        if not config_path.is_file():
            raise FileNotFoundError(f"config file is missing: {config_path}")
        relative = f"configs/{config_path.name}"
        if relative in seen_config_names:
            raise ValueError(f"duplicate config basename in handoff: {config_path.name}")
        seen_config_names.add(relative)
        shutil.copy2(config_path, output_dir / relative)
        config_hashes[relative] = sha256_file(output_dir / relative)
        copied_files.append(relative)

    run_sheet = (
        "# FalsiRAG external blind-test custodian run sheet\n\n"
        f"Frozen commit: `{frozen_commit}`\n\n"
        "Use only the included `blind_bundle/` directory as the data directory. "
        "Do not request or inspect adjudicated benchmark gold. Run each frozen model "
        "suite once with `--split test --allow-test`, return unscored suite directories "
        "and logs, and report every restart or failure.\n\n"
        "Example:\n\n"
        "```bash\n"
        "uv run falsirag-suite \\\n"
        "  --config configs/deepseek.yaml \\\n"
        "  --data-dir blind_bundle \\\n"
        "  --output-dir returned/deepseek_test_suite \\\n"
        "  --split test --allow-test\n"
        "```\n"
    )
    (output_dir / "CUSTODIAN_RUN_SHEET.md").write_text(run_sheet, encoding="utf-8")
    copied_files.append("CUSTODIAN_RUN_SHEET.md")
    result = {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "created_at": "not-recorded-deterministic-archive",
        "frozen_commit": frozen_commit,
        "allow_technical": allow_technical,
        "bundle_audit": audit,
        "config_files": config_hashes,
        "files": {relative: sha256_file(output_dir / relative) for relative in copied_files},
        "safety": {
            "gold_included": False,
            "source_benchmark_included": False,
            "adjudicated_benchmark_included": False,
            "local_scores_included": False,
            "credentials_included": False,
        },
        "archive_file": f"{output_dir.name}.zip",
        "archive_sha256": "",
    }
    manifest_path = output_dir / "custodian_handoff_manifest.json"
    write_json(manifest_path, result)
    copied_files.append("custodian_handoff_manifest.json")
    archive_path = output_dir.parent / f"{output_dir.name}.zip"
    if archive_path.exists():
        if not overwrite:
            raise FileExistsError(f"{archive_path} exists; pass overwrite=True to replace it")
        archive_path.unlink()
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in sorted(copied_files):
            info = zipfile.ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (output_dir / relative).read_bytes())
    result["archive_sha256"] = sha256_file(archive_path)
    write_json(manifest_path, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    build_parser.add_argument("--output-dir", type=Path, required=True)
    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("--bundle-dir", type=Path, required=True)
    audit_parser.add_argument("--allow-technical", action="store_true")
    package_parser = subparsers.add_parser("package")
    package_parser.add_argument("--bundle-dir", type=Path, required=True)
    package_parser.add_argument("--output-dir", type=Path, required=True)
    package_parser.add_argument("--config", type=Path, action="append", required=True)
    package_parser.add_argument("--frozen-commit", required=True)
    package_parser.add_argument("--overwrite", action="store_true")
    package_parser.add_argument("--allow-technical", action="store_true")
    # Backward-compatible direct build mode.
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.command == "audit":
        manifest = audit_bundle(args.bundle_dir, allow_technical=args.allow_technical)
    elif args.command == "package":
        manifest = package_handoff(
            args.bundle_dir,
            args.output_dir,
            config_paths=args.config,
            frozen_commit=args.frozen_commit,
            overwrite=args.overwrite,
            allow_technical=args.allow_technical,
        )
    else:
        data_dir = args.data_dir or DEFAULT_DATA_DIR
        output_dir = args.output_dir
        if output_dir is None:
            parser.error("build mode requires --output-dir")
        manifest = build(data_dir, output_dir)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
