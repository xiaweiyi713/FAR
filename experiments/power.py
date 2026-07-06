"""Power analysis and fail-closed G-P evidence for paired FAR experiments."""

from __future__ import annotations

import argparse
import json
import math
import random
import tempfile
from pathlib import Path
from typing import Any

from bench.build.common import sha256_file, write_json
from experiments.protocol_longterm import ROADMAP_ACTIVE_SHA256, verify_active_roadmap

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "diagnostics" / "power_v1"
DEFAULT_REPORT = ROOT / "reports" / "power_retrospective.md"
RELEASE_FILES = {"power_analysis.json", "power_retrospective.md", "manifest.json"}
POWER_THRESHOLD = 0.60
TARGET_EFFECT = 0.078
ALPHA = 0.05


def _validate_design(n: int, discordance_rate: float, effect: float) -> None:
    if n < 1:
        raise ValueError("power design requires n >= 1")
    if not 0.0 <= discordance_rate <= 1.0:
        raise ValueError("discordance_rate must be in [0, 1]")
    if abs(effect) > discordance_rate:
        raise ValueError("absolute paired effect cannot exceed discordance_rate")


def _mcnemar_p(baseline_only: int, candidate_only: int) -> float:
    discordant = baseline_only + candidate_only
    if discordant == 0:
        return 1.0
    tail = min(baseline_only, candidate_only)
    cumulative = sum(math.comb(discordant, value) for value in range(tail + 1))
    return float(min(1.0, 2.0 * cumulative / (2**discordant)))


def _binomial_probability(n: int, successes: int, probability: float) -> float:
    if probability == 0.0:
        return float(successes == 0)
    if probability == 1.0:
        return float(successes == n)
    return (
        math.comb(n, successes)
        * probability**successes
        * (1.0 - probability) ** (n - successes)
    )


def exact_mcnemar_power(
    n: int,
    discordance_rate: float,
    effect: float,
    *,
    alpha: float = ALPHA,
) -> float:
    """Exact power for a positive paired binary effect under a multinomial model."""

    _validate_design(n, discordance_rate, effect)
    if effect < 0:
        raise ValueError("G-P power is parameterized for a nonnegative target effect")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    if discordance_rate == 0.0:
        return 0.0
    candidate_share = (discordance_rate + effect) / (2.0 * discordance_rate)
    power = 0.0
    for discordant in range(n + 1):
        discordant_probability = _binomial_probability(
            n,
            discordant,
            discordance_rate,
        )
        for candidate_only in range(discordant + 1):
            baseline_only = discordant - candidate_only
            observed_effect = (candidate_only - baseline_only) / n
            if observed_effect <= 0.0 or _mcnemar_p(baseline_only, candidate_only) >= alpha:
                continue
            power += discordant_probability * _binomial_probability(
                discordant,
                candidate_only,
                candidate_share,
            )
    return power


def minimum_detectable_effect(
    n: int,
    discordance_rate: float,
    *,
    target_power: float = 0.80,
    alpha: float = ALPHA,
    tolerance: float = 1e-5,
) -> float | None:
    """Return the smallest positive paired effect reaching target exact power."""

    _validate_design(n, discordance_rate, 0.0)
    if not 0.0 < target_power < 1.0:
        raise ValueError("target_power must be in (0, 1)")
    if exact_mcnemar_power(n, discordance_rate, discordance_rate, alpha=alpha) < target_power:
        return None
    lower = 0.0
    upper = discordance_rate
    while upper - lower > tolerance:
        middle = (lower + upper) / 2.0
        if exact_mcnemar_power(n, discordance_rate, middle, alpha=alpha) >= target_power:
            upper = middle
        else:
            lower = middle
    return upper


def _simulate_family(
    rng: random.Random,
    n: int,
    discordance_rate: float,
    effect: float,
) -> tuple[int, int, list[int]]:
    _validate_design(n, discordance_rate, effect)
    candidate_only_probability = (discordance_rate + effect) / 2.0
    baseline_only_probability = (discordance_rate - effect) / 2.0
    candidate_only = 0
    baseline_only = 0
    differences: list[int] = []
    for _ in range(n):
        draw = rng.random()
        if draw < candidate_only_probability:
            candidate_only += 1
            differences.append(1)
        elif draw < candidate_only_probability + baseline_only_probability:
            baseline_only += 1
            differences.append(-1)
        else:
            differences.append(0)
    return baseline_only, candidate_only, differences


def simulate_mcnemar_power(
    n: int,
    discordance_rate: float,
    effect: float,
    *,
    simulations: int = 20_000,
    seed: int = 1729,
    alpha: float = ALPHA,
) -> dict[str, Any]:
    _validate_design(n, discordance_rate, effect)
    if effect < 0 or simulations < 1:
        raise ValueError("simulation requires nonnegative effect and simulations >= 1")
    rng = random.Random(seed)
    rejected = 0
    for _ in range(simulations):
        baseline_only, candidate_only, _ = _simulate_family(
            rng,
            n,
            discordance_rate,
            effect,
        )
        rejected += (
            candidate_only > baseline_only
            and _mcnemar_p(baseline_only, candidate_only) < alpha
        )
    return {
        "method": "paired-mcnemar-monte-carlo-v1",
        "n": n,
        "discordance_rate": discordance_rate,
        "target_effect": effect,
        "alpha": alpha,
        "simulations": simulations,
        "seed": seed,
        "power": rejected / simulations,
        "exact_power": exact_mcnemar_power(n, discordance_rate, effect, alpha=alpha),
    }


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _family_cluster_interval(
    family_differences: list[list[int]],
    *,
    resamples: int,
    rng: random.Random,
    confidence: float = 0.95,
) -> tuple[float, float]:
    if not family_differences or resamples < 1:
        raise ValueError("family cluster bootstrap requires families and resamples")
    summaries = [(sum(family), len(family)) for family in family_differences]
    estimates: list[float] = []
    for _ in range(resamples):
        sampled = [rng.choice(summaries) for _ in summaries]
        estimates.append(
            sum(total for total, _ in sampled) / sum(size for _, size in sampled)
        )
    alpha = (1.0 - confidence) / 2.0
    return _percentile(estimates, alpha), _percentile(estimates, 1.0 - alpha)


def simulate_stratified_power(
    family_designs: list[dict[str, float | int]],
    *,
    simulations: int = 10_000,
    bootstrap_resamples: int = 500,
    seed: int = 1729,
    alpha: float = ALPHA,
) -> dict[str, Any]:
    """Simulate pooled exact McNemar and family-cluster bootstrap power."""

    if not family_designs or simulations < 1 or bootstrap_resamples < 1:
        raise ValueError("stratified power requires designs and positive resample counts")
    normalized: list[dict[str, float | int]] = []
    for design in family_designs:
        n = int(design["n"])
        discordance = float(design["discordance_rate"])
        effect = float(design["effect"])
        _validate_design(n, discordance, effect)
        if effect < 0:
            raise ValueError("G-P family target effects must be nonnegative")
        normalized.append(
            {
                "n": n,
                "discordance_rate": discordance,
                "effect": effect,
            }
        )
    rng = random.Random(seed)
    mcnemar_rejected = 0
    cluster_rejected = 0
    direction_consistent = 0
    for _ in range(simulations):
        total_baseline_only = 0
        total_candidate_only = 0
        families: list[list[int]] = []
        positive_families = 0
        for design in normalized:
            baseline_only, candidate_only, differences = _simulate_family(
                rng,
                int(design["n"]),
                float(design["discordance_rate"]),
                float(design["effect"]),
            )
            total_baseline_only += baseline_only
            total_candidate_only += candidate_only
            positive_families += candidate_only > baseline_only
            families.append(differences)
        mcnemar_rejected += (
            total_candidate_only > total_baseline_only
            and _mcnemar_p(total_baseline_only, total_candidate_only) < alpha
        )
        direction_consistent += positive_families >= math.ceil(2 * len(normalized) / 3)
        lower, _ = _family_cluster_interval(
            families,
            resamples=bootstrap_resamples,
            rng=rng,
        )
        cluster_rejected += lower > 0.0
    return {
        "method": "family-stratified-power-monte-carlo-v1",
        "family_designs": normalized,
        "families": len(normalized),
        "pairs": sum(int(item["n"]) for item in normalized),
        "alpha": alpha,
        "simulations": simulations,
        "bootstrap_resamples": bootstrap_resamples,
        "seed": seed,
        "stratified_mcnemar_power": mcnemar_rejected / simulations,
        "family_cluster_bootstrap_power": cluster_rejected / simulations,
        "at_least_two_thirds_positive_probability": direction_consistent / simulations,
    }


def _source_summary() -> tuple[dict[str, Any], dict[str, str]]:
    component_path = ROOT / "diagnostics" / "attribution_v1" / "dev_component_attribution.json"
    round1_path = (
        ROOT
        / "diagnostics"
        / "ramdocs_v2"
        / "round1"
        / "comparisons"
        / "far_vs_multi_query_rag.json"
    )
    round2_path = (
        ROOT
        / "diagnostics"
        / "ramdocs_v2"
        / "round2"
        / "comparisons"
        / "far_vs_multi_query_rag.json"
    )
    component = json.loads(component_path.read_text(encoding="utf-8"))
    qwen_flips = component["flip_matrix"]["minus_typed_conflict"]["binary_flips"]
    qwen_candidate_only = int(qwen_flips.get("far_only", 0))
    qwen_baseline_only = int(qwen_flips.get("comparison_only", 0))
    sources: dict[str, Any] = {
        "qwen_dev": {
            "n": int(component["samples"]),
            "candidate_only": qwen_candidate_only,
            "baseline_only": qwen_baseline_only,
            "continuous_effect": float(
                component["flip_matrix"]["minus_typed_conflict"]["mean_continuous_delta"]
            ),
        }
    }
    for key, path in (("ramdocs_round1", round1_path), ("ramdocs_round2", round2_path)):
        comparison = json.loads(path.read_text(encoding="utf-8"))
        mcnemar = comparison["mcnemar"]
        sources[key] = {
            "n": int(comparison["comparison"]["pairs"]),
            "candidate_only": int(mcnemar["candidate_only"]),
            "baseline_only": int(mcnemar["baseline_only"]),
            "observed_effect": float(comparison["comparison"]["candidate_minus_baseline"]),
        }
    fingerprints = {
        str(path.relative_to(ROOT)): sha256_file(path)
        for path in (component_path, round1_path, round2_path)
    }
    return sources, fingerprints


def compute_retrospective(
    *,
    simulations: int = 10_000,
    bootstrap_resamples: int = 500,
    seed: int = 1729,
) -> dict[str, Any]:
    roadmap = verify_active_roadmap()
    sources, fingerprints = _source_summary()
    historical: dict[str, Any] = {}
    for key, source in sources.items():
        n = int(source["n"])
        discordant = int(source["candidate_only"]) + int(source["baseline_only"])
        discordance = discordant / n
        historical[key] = {
            **source,
            "discordant": discordant,
            "discordance_rate": discordance,
            "mde_60": minimum_detectable_effect(n, discordance, target_power=0.60),
            "mde_80": minimum_detectable_effect(n, discordance, target_power=0.80),
            "power_for_0_03": (
                exact_mcnemar_power(n, discordance, 0.03)
                if discordance >= 0.03
                else None
            ),
            "power_for_0_078": (
                exact_mcnemar_power(n, discordance, TARGET_EFFECT)
                if discordance >= TARGET_EFFECT
                else None
            ),
        }
    qwen_discordance = float(historical["qwen_dev"]["discordance_rate"])
    family_designs = [
        {"n": 60, "discordance_rate": qwen_discordance, "effect": TARGET_EFFECT}
        for _ in range(3)
    ]
    ws2 = simulate_stratified_power(
        family_designs,
        simulations=simulations,
        bootstrap_resamples=bootstrap_resamples,
        seed=seed,
    )
    primary_power = float(ws2["stratified_mcnemar_power"])
    adequately_powered = primary_power >= POWER_THRESHOLD
    return {
        "schema_version": "far-power-retrospective-v1",
        "roadmap_fingerprint": roadmap,
        "source_fingerprints": dict(sorted(fingerprints.items())),
        "historical": historical,
        "ws2_design": {
            **ws2,
            "target_effect_basis": "F1 qwen dev continuous typed-minus-untyped +0.078",
            "discordance_basis": "qwen dev binary flips at answer_correctness >= 0.8",
            "gate_p_threshold": POWER_THRESHOLD,
            "gate_p_completed": True,
            "adequately_powered": adequately_powered,
            "required_claim_level": (
                "confirmatory" if adequately_powered else "directional_reproduction"
            ),
            "g_f_failure_interpretation": (
                "may reject cross-family replication"
                if adequately_powered
                else "inconclusive for absence; report direction and interval"
            ),
        },
        "model_calls": 0,
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
    }


def _report_text(result: dict[str, Any]) -> str:
    historical = result["historical"]
    ws2 = result["ws2_design"]
    lines = [
        "# FAR 功效回顾与 G-P 门禁",
        "",
        "> 本报告只使用冻结 dev 配对计数；零模型调用、不访问 held-out/test，也不改变任何既有门禁。",
        "",
        "## 历史设计",
        "",
        "| 设计 | n | 不一致率 | MDE@60% | MDE@80% | power(+3pp) | power(+7.8pp) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    labels = {
        "qwen_dev": "Qwen dev typed/untyped",
        "ramdocs_round1": "RAMDocs Round 1",
        "ramdocs_round2": "RAMDocs Round 2",
    }
    for key in ("qwen_dev", "ramdocs_round1", "ramdocs_round2"):
        row = historical[key]

        def formatted(value: float | None) -> str:
            return "不可达" if value is None else f"{value:.3f}"

        lines.append(
            f"| {labels[key]} | {row['n']} | {row['discordance_rate']:.3f} | "
            f"{formatted(row['mde_60'])} | {formatted(row['mde_80'])} | "
            f"{formatted(row['power_for_0_03'])} | {formatted(row['power_for_0_078'])} |"
        )
    lines.extend(
        [
            "",
            "MDE 是在冻结不一致率下，双侧 exact McNemar 且方向为正时达到目标功效所需的最小配对差。"
            "它不是可接受效应阈值，也不能追溯性改写已完成实验。",
            "",
            "## WS2 三家族设计 (3 x 60 配对)",
            "",
            f"- 目标效应: +{TARGET_EFFECT:.3f}；不一致率沿用 Qwen dev "
            f"{historical['qwen_dev']['discordance_rate']:.3f}。",
            f"- 分层 exact McNemar 模拟功效: {ws2['stratified_mcnemar_power']:.3f}。",
            f"- 家族聚类 bootstrap 95% CI 下界 > 0 的概率: "
            f"{ws2['family_cluster_bootstrap_power']:.3f}。",
            f"- 至少 2/3 家族方向为正的概率: "
            f"{ws2['at_least_two_thirds_positive_probability']:.3f}。",
            f"- G-P 完成: `true`；充分功效: `{str(ws2['adequately_powered']).lower()}`；"
            f"强制研究级别: `{ws2['required_claim_level']}`。",
            "",
            "若充分功效为 false，G-F 不显著不得解释为 typed control 在跨家族上不存在；"
            "只能报告方向、效应量与区间。方向不一致仍可按预注册规则收窄为 Qwen-specific。",
            "",
            "## 制度化规则",
            "",
            "所有后续正式预注册必须记录 n、不一致率依据、目标效应、alpha、模拟次数、种子、"
            "主检验功效及 claim level。主功效 <0.60 时只能登记为方向性/描述性研究；"
            "不得以事后换指标、换子集或增加一轮运行改变级别。",
            "",
        ]
    )
    return "\n".join(lines)


def build_release(
    output_dir: Path = DEFAULT_OUTPUT,
    report_path: Path = DEFAULT_REPORT,
    *,
    simulations: int = 10_000,
    bootstrap_resamples: int = 500,
    seed: int = 1729,
) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"{output_dir} is nonempty")
    result = compute_retrospective(
        simulations=simulations,
        bootstrap_resamples=bootstrap_resamples,
        seed=seed,
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    write_json(output_dir / "power_analysis.json", result)
    report = _report_text(result)
    (output_dir / "power_retrospective.md").write_text(report, encoding="utf-8")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    manifest = {
        "schema_version": "far-power-release-v1",
        "roadmap_fingerprint": ROADMAP_ACTIVE_SHA256,
        "artifacts": {
            name: sha256_file(output_dir / name)
            for name in ("power_analysis.json", "power_retrospective.md")
        },
        "external_report_sha256": sha256_file(report_path),
        "source_fingerprints": result["source_fingerprints"],
        "gate_p_completed": True,
        "adequately_powered": result["ws2_design"]["adequately_powered"],
        "required_claim_level": result["ws2_design"]["required_claim_level"],
        "model_calls": 0,
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def verify_release(
    output_dir: Path = DEFAULT_OUTPUT,
    report_path: Path = DEFAULT_REPORT,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
        analysis = json.loads((output_dir / "power_analysis.json").read_text(encoding="utf-8"))
        simulation = analysis["ws2_design"]
        with tempfile.TemporaryDirectory(prefix="far-power-verify-") as temporary:
            rebuilt_dir = Path(temporary) / "release"
            rebuilt_report = Path(temporary) / "power.md"
            build_release(
                rebuilt_dir,
                rebuilt_report,
                simulations=int(simulation["simulations"]),
                bootstrap_resamples=int(simulation["bootstrap_resamples"]),
                seed=int(simulation["seed"]),
            )
            if {path.name for path in output_dir.iterdir() if path.is_file()} != RELEASE_FILES:
                errors.append("power release file set is not exact")
            for name in RELEASE_FILES:
                if (output_dir / name).read_bytes() != (rebuilt_dir / name).read_bytes():
                    errors.append(f"power artifact differs from recomputation: {name}")
            if report_path.read_bytes() != rebuilt_report.read_bytes():
                errors.append("external power report differs from recomputation")
        expected = {
            "schema_version": "far-power-release-v1",
            "roadmap_fingerprint": ROADMAP_ACTIVE_SHA256,
            "gate_p_completed": True,
            "model_calls": 0,
            "publication_gold": False,
            "human_iaa": False,
            "test_accessed": False,
        }
        for key, value in expected.items():
            if manifest.get(key) != value:
                errors.append(f"power manifest field mismatch: {key}")
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    return {
        "schema_version": "far-power-release-audit-v1",
        "valid": not errors,
        "errors": errors,
        "gate_p_completed": not errors,
        "model_calls": 0,
        "publication_gold": False,
        "human_iaa": False,
        "test_accessed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    simulate = subparsers.add_parser("simulate")
    simulate.add_argument("--n", type=int, required=True)
    simulate.add_argument("--discordance-rate", type=float, required=True)
    simulate.add_argument("--effect", type=float, required=True)
    simulate.add_argument("--simulations", type=int, default=20_000)
    simulate.add_argument("--seed", type=int, default=1729)
    build = subparsers.add_parser("build")
    build.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    build.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    build.add_argument("--simulations", type=int, default=10_000)
    build.add_argument("--bootstrap-resamples", type=int, default=500)
    build.add_argument("--seed", type=int, default=1729)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    verify.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    if args.command == "simulate":
        result = simulate_mcnemar_power(
            args.n,
            args.discordance_rate,
            args.effect,
            simulations=args.simulations,
            seed=args.seed,
        )
    elif args.command == "build":
        result = build_release(
            args.output_dir,
            args.report,
            simulations=args.simulations,
            bootstrap_resamples=args.bootstrap_resamples,
            seed=args.seed,
        )
    else:
        result = verify_release(args.output_dir, args.report)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.command == "verify" and result.get("valid") is not True:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
