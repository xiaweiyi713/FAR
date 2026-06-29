"""FAR evaluation metrics and statistical inference."""

from .metrics import PredictionRecord, aggregate_scores, score_sample
from .stats import (
    dependency_cluster_bootstrap_ci,
    mcnemar_exact,
    paired_bootstrap_comparison,
    stratified_bootstrap_ci,
)

__all__ = [
    "PredictionRecord",
    "aggregate_scores",
    "dependency_cluster_bootstrap_ci",
    "mcnemar_exact",
    "paired_bootstrap_comparison",
    "score_sample",
    "stratified_bootstrap_ci",
]
