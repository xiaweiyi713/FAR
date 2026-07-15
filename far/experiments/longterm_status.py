"""Generate a status ledger for the post-stop-rule long-term FAR roadmap.

The ledger is deliberately read-only. It inspects tracked reports, manifests,
protocol fingerprints, and public documentation to show where WS1--WS6 stand.
It does not score predictions, call models, access held-out/test data, or change
any experimental gate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from far.bench.build.common import sha256_file, write_json
from far.experiments.evidence_boundary import verify_release as verify_boundary_release
from far.experiments.evidence_family_dev import verify_release as verify_family_dev_release
from far.experiments.protocol_boundary import verify_boundary_protocol
from far.experiments.protocol_family_dev import verify_family_protocol
from far.experiments.protocol_longterm import FROZEN_FACT_IDS, ROOT, verify_active_roadmap
from far.experiments.repository_maintenance import audit as audit_repository_maintenance

SCHEMA_VERSION = "far-longterm-roadmap-status-v1"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _file_record(root: Path, path: Path, *, include_sha256: bool = True) -> dict[str, Any]:
    exists = path.is_file()
    return {
        "path": _rel(root, path),
        "exists": exists,
        "sha256": sha256_file(path) if exists and include_sha256 else None,
    }


def _roadmap(root: Path) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    try:
        fingerprint: str | None = verify_active_roadmap()
    except ValueError as exc:
        fingerprint = None
        errors.append(str(exc))
    text = _read_text(root / "docs/PLAN_LONGTERM_OPTIMIZATION.md")
    missing_facts = [fact for fact in FROZEN_FACT_IDS if f"| {fact} |" not in text]
    if missing_facts:
        errors.append(f"frozen fact rows missing: {', '.join(missing_facts)}")
    return (
        {
            "path": "docs/PLAN_LONGTERM_OPTIMIZATION.md",
            "active_sha256": fingerprint,
            "frozen_fact_ids": list(FROZEN_FACT_IDS),
            "frozen_facts_present": not missing_facts,
            "missing_facts": missing_facts,
        },
        errors,
    )


def _ws1(root: Path) -> dict[str, Any]:
    manifest_path = root / "diagnostics/attribution_v1/manifest.json"
    report_path = root / "reports/mechanism_attribution.md"
    errors: list[str] = []
    try:
        manifest = _json(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        manifest = {}
        errors.append(str(exc))
    hypotheses = manifest.get("hypothesis_statuses", {})
    expected_hypotheses = {"H-upstream", "H-conflict-shape", "H-metric", "H-component"}
    complete = (
        manifest.get("gate_r1_passed") is True
        and manifest.get("both_incorrect_samples") == 226
        and manifest.get("ramdocs_samples") == 350
        and manifest.get("model_calls") == 0
        and manifest.get("test_accessed") is False
        and set(hypotheses) == expected_hypotheses
        and report_path.is_file()
    )
    if not complete and not errors:
        errors.append("WS1 G-R1 evidence is incomplete or missing required safeguards")
    return {
        "name": "WS1 mechanism attribution",
        "priority": "P0",
        "status": "complete" if complete else "incomplete",
        "gate": "G-R1",
        "gate_passed": bool(manifest.get("gate_r1_passed")),
        "model_calls": manifest.get("model_calls"),
        "test_accessed": manifest.get("test_accessed"),
        "human_iaa": manifest.get("human_iaa"),
        "summary": "226 shared RAMDocs errors uniquely bucketed; four hypotheses recorded",
        "key_evidence": [_file_record(root, manifest_path), _file_record(root, report_path)],
        "details": {
            "bucket_counts": manifest.get("bucket_counts"),
            "hypothesis_statuses": hypotheses,
        },
        "errors": errors,
    }


def _ws2(root: Path) -> dict[str, Any]:
    protocol = verify_family_protocol()
    release_manifest = root / "diagnostics/family_dev_v1/manifest.json"
    current_state = root / "docs/CURRENT_OPERATIONAL_STATE.md"
    release_exists = release_manifest.is_file()
    current_text = _read_text(current_state)
    active_run_documented = (
        (
            "far-family-dev-mistral-resume.service" in current_text
            or "far-family-dev@google.service" in current_text
            or "far-family-dev@meta.service" in current_text
        )
        and "`active`" in current_text
        and "当前进度" in current_text
        and "当前日志位置" in current_text
    )
    mistral_complete_paused_documented = (
        "WS2 Mistral family 已完整完成" in current_text
        and "Google/Gemma" in current_text
        and "`inactive`" in current_text
        and "今晚暂停" in current_text
    )
    google_preflight_documented = (
        "scripts/preflight_windows_family_dev_next.sh google" in current_text
        and "valid=true" in current_text
    )
    guarded_starter_documented = (
        "scripts/start_windows_family_dev_next.sh google" in current_text
        and "--execute" in current_text
    )
    google_started_paused_documented = (
        "Google/Gemma 已按 guarded starter 启动后暂停" in current_text
        and "calibration/google/far/checkpoint.jsonl" in current_text
        and "`2` 行" in current_text
        and "`inactive`" in current_text
        and "今晚不再训练" in current_text
    )
    paused_checkpoint_documented = "minus_typed_conflict" in current_text and "7/60" in current_text
    errors = [f"protocol: {item}" for item in protocol.get("errors", [])]
    release_audit: dict[str, Any] = {}
    if release_exists:
        try:
            release_audit = verify_family_dev_release(release_manifest.parent)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"release audit failed: {exc}")
        if release_audit.get("valid") is True:
            status = "complete"
            summary = (
                "verified three-family directional reproduction; G-F passed with 3/3 "
                "positive family directions"
            )
        else:
            status = "release_present_invalid"
            summary = "local family-dev release exists but independent verification failed"
            errors.extend(f"release: {item}" for item in release_audit.get("errors", []))
    elif active_run_documented:
        status = "in_progress_active"
        summary = "a WS2 single-family dev run is active on the Windows GPU"
    elif google_started_paused_documented:
        status = "in_progress_paused"
        summary = "Google/Gemma is paused after 2 FAR calibration checkpoints"
    elif mistral_complete_paused_documented:
        status = "in_progress_paused"
        summary = (
            "Mistral family is complete; next registered family waits for the next training window"
        )
    elif paused_checkpoint_documented:
        status = "in_progress_paused"
        summary = "Mistral FAR complete remotely; Mistral untyped paused at documented checkpoint"
    else:
        status = "registered_pending_or_remote_unknown"
        summary = "protocol registered; local final release is not present"
    return {
        "name": "WS2 cross-family typed/untyped dev reproduction",
        "priority": "P0",
        "status": status,
        "gate": "G-F",
        "gate_passed": (
            release_audit.get("gate_f_passed") if release_audit.get("valid") is True else None
        ),
        "protocol_valid": bool(protocol.get("valid")),
        "required_claim_level": protocol.get("required_claim_level"),
        "test_accessed": protocol.get("test_accessed"),
        "human_iaa": protocol.get("human_iaa"),
        "summary": summary,
        "key_evidence": [
            _file_record(root, root / "docs/PLAN_FAMILY_DEV.md"),
            _file_record(root, current_state),
            _file_record(root, release_manifest),
        ],
        "details": {
            "families": protocol.get("families"),
            "methods": protocol.get("methods"),
            "samples": protocol.get("samples"),
            "local_release_present": release_exists,
            "release_verified": release_audit.get("valid") is True,
            "direction_consistent": release_audit.get("direction_consistent"),
            "active_run_documented": active_run_documented,
            "mistral_complete_paused_documented": mistral_complete_paused_documented,
            "google_preflight_documented": google_preflight_documented,
            "guarded_starter_documented": guarded_starter_documented,
            "google_started_paused_documented": google_started_paused_documented,
            "paused_checkpoint_documented": paused_checkpoint_documented,
        },
        "errors": errors,
    }


def _ws3(root: Path) -> dict[str, Any]:
    protocol = verify_boundary_protocol()
    release_manifest = root / "diagnostics/boundary_v1/manifest.json"
    matrix = root / "reports/boundary_matrix.md"
    release_exists = release_manifest.is_file()
    errors = [f"protocol: {item}" for item in protocol.get("errors", [])]
    release_audit: dict[str, Any] = {}
    if release_exists and matrix.is_file():
        try:
            release_audit = verify_boundary_release(release_manifest.parent, matrix)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"release audit failed: {exc}")
        if release_audit.get("valid") is True:
            status = "complete"
            summary = (
                "verified public-dev boundary matrix; result supports directional boundary "
                "mapping rather than a global win/loss claim"
            )
        else:
            status = "release_present_invalid"
            summary = "boundary release artifacts exist but independent verification failed"
            errors.extend(f"release: {item}" for item in release_audit.get("errors", []))
    else:
        status = "registered_inputs_ready_pending_predictions"
        summary = "two public dev imports and protocol are frozen; no model predictions yet"
    return {
        "name": "WS3 external boundary mapping",
        "priority": "P1",
        "status": status,
        "gate": "G-B",
        "gate_passed": (
            release_audit.get("gate_b_complete") if release_audit.get("valid") is True else None
        ),
        "protocol_valid": bool(protocol.get("valid")),
        "required_claim_level": release_audit.get(
            "required_claim_level", protocol.get("required_claim_level")
        ),
        "test_accessed": release_audit.get("test_accessed", protocol.get("test_accessed")),
        "human_iaa": release_audit.get("human_iaa", protocol.get("human_iaa")),
        "summary": summary,
        "key_evidence": [
            _file_record(root, root / "docs/PLAN_BOUNDARY_MAPPING.md"),
            _file_record(root, root / "reports/boundary_benchmark_selection.md"),
            _file_record(root, release_manifest),
            _file_record(root, matrix),
        ],
        "details": {
            "datasets": protocol.get("datasets"),
            "methods": protocol.get("methods"),
            "samples_per_dataset": protocol.get("samples_per_dataset"),
            "local_release_present": release_exists,
            "release_verified": release_audit.get("valid") is True,
            "global_pass_fail": release_audit.get("global_pass_fail"),
        },
        "errors": errors,
    }


def _ws4(root: Path) -> dict[str, Any]:
    status_path = root / "paper/STATUS.md"
    main_path = root / "paper/main.tex"
    readiness_path = root / "reports/solo_paper_readiness.json"
    integration_path = root / "reports/tmlr_result_integration_matrix.md"
    status_text = _read_text(status_path)
    main_text = _read_text(main_path)
    integration_text = _read_text(integration_path)
    errors: list[str] = []
    try:
        readiness = _json(readiness_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        readiness = {}
        errors.append(str(exc))
    tmlr_relocated = "TMLR mechanism-and-boundary study" in status_text
    strict_inactive = "strict AAAI profile receives no further investment" in status_text
    boundary_claim = (
        "instrumented FAR case study" in main_text
        and "public-development applicability boundary" in main_text
    )
    ws3_integrated = (
        "global typed-minus-untyped boundary-score differences are near zero" in main_text
        and "outdated-information subgroup" in main_text
        and "weak A-line" in status_text
        and "WS3 is also independently" in integration_text
        and "verified: WikiContradict" in integration_text
    )
    integration_matrix_present = (
        "A-line" in integration_text
        and "B-line" in integration_text
        and "C-line" in integration_text
        and "held-out/test policy" in integration_text
    )
    ready_relaxed = readiness.get("ready") is True
    if not (
        tmlr_relocated
        and strict_inactive
        and boundary_claim
        and ws3_integrated
        and integration_matrix_present
        and ready_relaxed
    ):
        errors.append("WS4 paper relocation evidence is incomplete")
    return {
        "name": "WS4 paper and venue repositioning",
        "priority": "P0",
        "status": "complete" if not errors else "incomplete",
        "gate": "paper readiness / claim scope",
        "gate_passed": ready_relaxed,
        "test_accessed": False,
        "human_iaa": False,
        "summary": "verified WS2 and WS3 are integrated into the TMLR mechanism-and-boundary draft",
        "key_evidence": [
            _file_record(root, status_path),
            _file_record(root, main_path),
            _file_record(root, readiness_path),
            _file_record(root, integration_path),
        ],
        "details": {
            "tmlr_relocated": tmlr_relocated,
            "strict_aaai_inactive": strict_inactive,
            "result_integration_matrix_present": integration_matrix_present,
            "relaxed_machine_audited_paper_ready": ready_relaxed,
            "ws2_integrated": "WS2 is now complete and independently verified" in status_text,
            "ws3_integrated": ws3_integrated,
            "waiting_for_ws3": False,
        },
        "errors": errors,
    }


def _ws5(root: Path) -> dict[str, Any]:
    manifest_path = root / "diagnostics/power_v1/manifest.json"
    report_path = root / "reports/power_retrospective.md"
    errors: list[str] = []
    try:
        manifest = _json(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        manifest = {}
        errors.append(str(exc))
    complete = (
        manifest.get("gate_p_completed") is True
        and manifest.get("required_claim_level") == "directional_reproduction"
        and manifest.get("model_calls") == 0
        and manifest.get("test_accessed") is False
        and report_path.is_file()
    )
    if not complete and not errors:
        errors.append("WS5 G-P release is incomplete")
    return {
        "name": "WS5 statistical design upgrade",
        "priority": "P1",
        "status": "complete" if complete else "incomplete",
        "gate": "G-P",
        "gate_passed": bool(manifest.get("gate_p_completed")),
        "required_claim_level": manifest.get("required_claim_level"),
        "model_calls": manifest.get("model_calls"),
        "test_accessed": manifest.get("test_accessed"),
        "human_iaa": manifest.get("human_iaa"),
        "summary": "power gate is institutionalized; WS2 forced to directional reproduction",
        "key_evidence": [_file_record(root, manifest_path), _file_record(root, report_path)],
        "details": {
            "adequately_powered": manifest.get("adequately_powered"),
            "external_report_sha256": manifest.get("external_report_sha256"),
        },
        "errors": errors,
    }


def _ws6(root: Path) -> dict[str, Any]:
    report = audit_repository_maintenance(root)
    status = "baseline_complete_ongoing_maintenance" if report.get("valid") else "incomplete"
    return {
        "name": "WS6 engineering maintenance",
        "priority": "P2",
        "status": status,
        "gate": "repository-maintenance audit",
        "gate_passed": bool(report.get("valid")),
        "test_accessed": False,
        "human_iaa": False,
        "summary": "tracked diagnostics size and output/outputs hygiene are machine-audited",
        "key_evidence": [
            # Avoid a cyclic freshness dependency: repository-maintenance
            # records tracked-file size, which includes this long-term ledger,
            # while this ledger summarizes WS6.  Existence plus the recomputed
            # audit result below is the stable evidence; hashing the generated
            # maintenance ledger here makes the two ledgers chase each other.
            _file_record(
                root,
                root / "reports/repository_maintenance.json",
                include_sha256=False,
            ),
            _file_record(
                root,
                root / "reports/repository_maintenance.md",
                include_sha256=False,
            ),
        ],
        "details": {
            "diagnostics_mib": report.get("diagnostics", {}).get("mib"),
            "tracked_files": report.get("tracked_files", {}).get("count"),
            "outputs_tracks_only_gitkeep": report.get("ignored_outputs", {}).get(
                "outputs_tracks_only_gitkeep"
            ),
        },
        "errors": report.get("errors", []),
    }


def build_status(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    roadmap, roadmap_errors = _roadmap(root)
    workstreams = {
        "WS1": _ws1(root),
        "WS2": _ws2(root),
        "WS3": _ws3(root),
        "WS4": _ws4(root),
        "WS5": _ws5(root),
        "WS6": _ws6(root),
    }
    errors = list(roadmap_errors)
    for key, row in workstreams.items():
        errors.extend(f"{key}: {error}" for error in row.get("errors", []))
    complete_statuses = {"complete", "baseline_complete_ongoing_maintenance"}
    complete_workstreams = [
        key for key, row in workstreams.items() if row.get("status") in complete_statuses
    ]
    incomplete_workstreams = [
        key for key, row in workstreams.items() if row.get("status") not in complete_statuses
    ]
    ws2_status = str(workstreams["WS2"].get("status"))
    ws2_details = workstreams["WS2"].get("details", {})
    ws3_status = str(workstreams["WS3"].get("status"))
    ws4_status = str(workstreams["WS4"].get("status"))
    goal_complete = not errors and not incomplete_workstreams
    if goal_complete:
        next_training_step = (
            "no required roadmap work remains; maintain the immutable diagnostic and paper "
            "releases plus their independent verifiers; P14 v1 remains retired unscored at 10 "
            "rows, while exact-tag v2 completed a fresh reference-free, group-disjoint 120-row "
            "run with isolated cache, zero v1 reuse, and registered evaluation_success; maintain "
            "the tracked P14 report/readiness v6 and prepare a new versioned portable evidence "
            "release without changing historical releases; no required GPU experiment remains, "
            "and external publication or submission remains an author-owned action"
        )
    elif ws2_status == "complete" and ws3_status == "complete" and ws4_status != "complete":
        next_training_step = (
            "integrate the verified WS3 boundary matrix into the TMLR paper and update the "
            "A/B/C decision-tree narrative; no further GPU work is needed tonight"
        )
    elif ws2_status == "complete":
        next_training_step = (
            "prepare the Windows worktree at latest main and start the registered WS3 "
            "public-dev boundary mapping only after its guarded preflight passes"
        )
    elif ws2_status == "in_progress_active":
        next_training_step = (
            "monitor the active WS2 single-family dev run until it completes or fails"
        )
    elif ws2_details.get("google_started_paused_documented") is True:
        next_training_step = (
            "when training is allowed tomorrow, dry-run the guarded Google/Gemma "
            "starter, then resume WS2 Google/Gemma from the documented checkpoint "
            "with FAR_FAMILY_DEV_TRAINING_ALLOWED=1"
        )
    elif ws2_details.get("mistral_complete_paused_documented") is True:
        if ws2_details.get("google_preflight_documented") is True:
            if ws2_details.get("guarded_starter_documented") is True:
                next_training_step = (
                    "when training is allowed, dry-run the guarded Google/Gemma starter, "
                    "then execute it with FAR_FAMILY_DEV_TRAINING_ALLOWED=1 to verify "
                    "Ollama digest and start WS2 Google/Gemma"
                )
            else:
                next_training_step = (
                    "when training is allowed, rerun Google/Gemma preflight with Ollama "
                    "digest verification and start WS2 Google/Gemma"
                )
        else:
            next_training_step = (
                "when training is allowed, verify Mistral manifests again and start "
                "WS2 Google/Gemma as the next preregistered family"
            )
    else:
        next_training_step = (
            "resume WS2 Mistral minus_typed_conflict from documented checkpoint "
            "only when training is allowed"
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "valid": not errors,
        "claim_scope": (
            "roadmap status only; does not alter F1-F10, experimental gates, "
            "label level, or held-out/test policy"
        ),
        "roadmap": roadmap,
        "workstreams": workstreams,
        "progress": {
            "complete_workstreams": complete_workstreams,
            "incomplete_workstreams": incomplete_workstreams,
            "goal_complete": goal_complete,
            "next_training_step": next_training_step,
        },
        "safety": {
            "model_calls": 0,
            "held_out_test_accessed": False,
            "can_claim_human_iaa": False,
            "can_claim_publication_gold": False,
        },
        "errors": errors,
    }


def render_markdown(report: dict[str, Any]) -> str:
    rows = []
    for key in ("WS1", "WS2", "WS3", "WS4", "WS5", "WS6"):
        row = report["workstreams"][key]
        rows.append(
            "| {key} | `{status}` | {gate} | {summary} |".format(
                key=key,
                status=row["status"],
                gate=row["gate"],
                summary=row["summary"],
            )
        )
    complete = ", ".join(report["progress"]["complete_workstreams"]) or "none"
    incomplete = ", ".join(report["progress"]["incomplete_workstreams"]) or "none"
    errors = "\n".join(f"- `{error}`" for error in report["errors"]) or "- 无"
    roadmap = report["roadmap"]
    return f"""# FAR 长期路线状态账本

本报告由已跟踪的 manifest、报告和协议指纹生成，用于显示
`docs/PLAN_LONGTERM_OPTIMIZATION.md` 的 WS1-WS6 当前状态。它不是投稿豁免、
不是新实验结果，也不改变 F1-F10、任何门禁、标签级别或 held-out/test 政策。

## 路线指纹

- 路线文件: `{roadmap["path"]}`
- 活动 SHA-256: `{roadmap["active_sha256"]}`
- F1-F10 行存在: `{str(roadmap["frozen_facts_present"]).lower()}`

## 工作流状态

| 工作流 | 状态 | 门禁/证据 | 摘要 |
|---|---|---|---|
{chr(10).join(rows)}

## 进度解释

- 已闭合或已建立基线: {complete}
- 仍未完成: {incomplete}
- 总目标完成: `{str(report["progress"]["goal_complete"]).lower()}`
- 当前首要动作: {report["progress"]["next_training_step"]}

## 安全边界

- 本报告模型调用: `0`
- 本报告访问 held-out/test: `false`
- 可声称 human IAA: `false`
- 可声称 publication gold: `false`

## 错误

{errors}
"""


def verify_outputs(root: Path, json_path: Path, markdown_path: Path) -> dict[str, Any]:
    expected = build_status(root)
    expected_markdown = render_markdown(expected)
    errors = list(expected["errors"])
    try:
        observed_json = _json(json_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        observed_json = None
        errors.append(f"JSON status unreadable: {exc}")
    if observed_json is not None and observed_json != expected:
        errors.append("JSON long-term status is stale; regenerate it")
    try:
        observed_markdown = markdown_path.read_text(encoding="utf-8")
    except OSError as exc:
        observed_markdown = ""
        errors.append(f"Markdown status unreadable: {exc}")
    if observed_markdown and observed_markdown != expected_markdown:
        errors.append("Markdown long-term status is stale; regenerate it")
    return {
        "schema_version": "far-longterm-roadmap-status-check-v1",
        "valid": not errors,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--json-output",
        type=Path,
        default=ROOT / "reports/longterm_roadmap_status.json",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=ROOT / "reports/longterm_roadmap_status.md",
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    if args.check:
        result = verify_outputs(root, args.json_output, args.markdown_output)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        if result.get("valid") is not True:
            raise SystemExit(1)
        return

    report = build_status(root)
    if args.json_output:
        write_json(args.json_output, report)
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
