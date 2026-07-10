"""FAR evaluation metrics and statistical inference."""

from .metrics import PredictionRecord, aggregate_scores, score_sample
from .stats import (
    dependency_cluster_bootstrap_ci,
    dependency_cluster_typed_conflict_f1_ci,
    mcnemar_exact,
    paired_bootstrap_comparison,
    paired_typed_conflict_f1_comparison,
    stratified_bootstrap_ci,
    stratified_typed_conflict_f1_ci,
)

__all__ = [
    "PredictionRecord",
    "aggregate_scores",
    "dependency_cluster_bootstrap_ci",
    "dependency_cluster_typed_conflict_f1_ci",
    "mcnemar_exact",
    "paired_bootstrap_comparison",
    "paired_typed_conflict_f1_comparison",
    "score_sample",
    "stratified_bootstrap_ci",
    "stratified_typed_conflict_f1_ci",
]
