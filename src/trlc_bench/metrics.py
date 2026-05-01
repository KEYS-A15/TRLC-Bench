"""
TRLCBench repair quality metrics.

Metrics:
  - is_valid:              Does the repaired plan pass structural validation?
  - makespan_delta:        Relative change in makespan
  - temporal_deviation:    Sum of absolute start-time shifts across matched actions
  - action_count_delta:    Net actions added/removed
  - constraint_retention:  Fraction of original ordering+mutex constraints still held
  - slack:                 Time remaining before nearest deadline
  - robustness:            Estimated tolerance for further perturbation
  - trlc_score:            Weighted composite ∈ [0, 100]

Design principle: metrics must discriminate between repair strategies.
If two strategies get the same score, the metric is useless. The naive
replan baseline should score POORLY on deviation/retention even when valid.
"""

from __future__ import annotations

from trlc_bench.models import (
    DomainConfig,
    RepairMetrics,
    TemporalPlan,
)
from trlc_bench.validator import validate_plan


def compute_metrics(
    original: TemporalPlan,
    repaired: TemporalPlan,
    config: DomainConfig,
    weights: dict[str, float] | None = None,
) -> RepairMetrics:
    """
    Compute the full TRLCBench scorecard for a repair attempt.

    Args:
        original: The original (pre-disruption) valid plan.
        repaired: The repaired plan to evaluate.
        config: Domain configuration for validation and deadline info.
        weights: Optional custom weights for the composite score.
                 Keys: "validity", "makespan", "deviation",
                        "retention", "robustness"

    Returns:
        RepairMetrics with all individual scores and composite.
    """
    if weights is None:
        weights = {
            "validity": 0.30,
            "makespan": 0.10,
            "deviation": 0.20,
            "retention": 0.20,
            "robustness": 0.20,
        }

    # 1. Validity
    validation = validate_plan(repaired, config)
    is_valid = validation.is_valid

    # 2. Makespan
    ms_orig = original.makespan
    ms_repair = repaired.makespan
    makespan_delta = (
        (ms_repair - ms_orig) / ms_orig if ms_orig > 0 else 0.0
    )

    # 3. Temporal deviation: sum of |start_time shifts| for matched actions
    temporal_deviation = _compute_temporal_deviation(original, repaired)

    # 4. Action count delta
    action_count_delta = repaired.num_actions - original.num_actions

    # 5. Constraint retention
    constraint_retention = _compute_constraint_retention(original, repaired, config)

    # 6. Slack (time before nearest deadline)
    slack = _compute_slack(repaired, config)

    # 7. Robustness estimate
    robustness = _compute_robustness(repaired, config)

    # 8. Composite TRLCScore
    trlc_score = _compute_composite(
        is_valid=is_valid,
        makespan_delta=makespan_delta,
        temporal_deviation=temporal_deviation,
        constraint_retention=constraint_retention,
        robustness=robustness,
        original_makespan=ms_orig,
        weights=weights,
    )

    return RepairMetrics(
        is_valid=is_valid,
        makespan_original=ms_orig,
        makespan_repaired=ms_repair,
        makespan_delta=makespan_delta,
        temporal_deviation=temporal_deviation,
        action_count_delta=action_count_delta,
        constraint_retention=constraint_retention,
        slack=slack,
        robustness=robustness,
        trlc_score=trlc_score,
    )


# ---------------------------------------------------------------------------
# Individual metric computations
# ---------------------------------------------------------------------------

def _compute_temporal_deviation(
    original: TemporalPlan, repaired: TemporalPlan
) -> float:
    """
    Sum of absolute start-time differences for actions present in both plans.

    Matched by (name, args) pair. Unmatched actions contribute their
    full start_time as deviation (they were inserted or moved completely).
    """
    orig_map: dict[tuple[str, ...], float] = {}
    for a in original.actions:
        key = (a.name, *a.args)
        orig_map[key] = a.start_time

    total_dev = 0.0
    matched = 0
    for a in repaired.actions:
        key = (a.name, *a.args)
        if key in orig_map:
            total_dev += abs(a.start_time - orig_map[key])
            matched += 1
        else:
            # Inserted action — full deviation
            total_dev += a.start_time + a.duration

    # Actions in original but not in repaired — penalize
    repaired_keys = {(a.name, *a.args) for a in repaired.actions}
    for key, start in orig_map.items():
        if key not in repaired_keys:
            total_dev += start

    return total_dev


def _compute_constraint_retention(
    original: TemporalPlan,
    repaired: TemporalPlan,
    config: DomainConfig,
) -> float:
    """
    Fraction of ordering and mutex constraints from the config that
    are satisfied by the repaired plan.
    """
    total = 0
    satisfied = 0

    # Ordering constraints
    for before_name, after_name in config.ordering_constraints:
        befores = repaired.get_actions_by_name(before_name)
        afters = repaired.get_actions_by_name(after_name)

        if not befores or not afters:
            continue  # Can't check if actions are missing

        total += 1
        for after_a in afters:
            if any(b.end_time <= after_a.start_time + 1e-9 for b in befores):
                satisfied += 1
                break

    # Mutex constraints
    for name_a, name_b in config.mutex_actions:
        as_a = repaired.get_actions_by_name(name_a)
        as_b = repaired.get_actions_by_name(name_b)

        for a in as_a:
            for b in as_b:
                total += 1
                if not a.overlaps(b):
                    satisfied += 1

    return satisfied / total if total > 0 else 1.0


def _compute_slack(repaired: TemporalPlan, config: DomainConfig) -> float:
    """
    Minimum slack across all deadline constraints.
    Slack = deadline - action_end_time. Negative means violated.
    """
    if not config.deadlines:
        return float("inf")

    min_slack = float("inf")
    for action_name, deadline in config.deadlines.items():
        for a in repaired.get_actions_by_name(action_name):
            slack = deadline - a.end_time
            min_slack = min(min_slack, slack)

    return min_slack if min_slack != float("inf") else 0.0


def _compute_robustness(repaired: TemporalPlan, config: DomainConfig) -> float:
    """
    Robustness estimate: normalized slack on the critical path.

    A plan with 0 slack is fragile (robustness=0).
    A plan with slack >= 20% of makespan is reasonably robust.
    Capped at [0, 1].
    """
    slack = _compute_slack(repaired, config)
    makespan = repaired.makespan

    if makespan <= 0:
        return 0.0
    if slack < 0:
        return 0.0

    # Normalize: slack / (20% of makespan) capped at 1.0
    normalized = slack / (0.2 * makespan)
    return min(1.0, max(0.0, normalized))


def _compute_composite(
    is_valid: bool,
    makespan_delta: float,
    temporal_deviation: float,
    constraint_retention: float,
    robustness: float,
    original_makespan: float,
    weights: dict[str, float],
) -> float:
    """
    Compute the composite TRLCScore ∈ [0, 100].

    Components (each normalized to [0, 1]):
      - validity:   1.0 if valid, 0.0 if not
      - makespan:   1.0 if no change, decreasing with increase
      - deviation:  1.0 if no shift, decreasing with total shift
      - retention:  directly from constraint_retention
      - robustness: directly from robustness estimate
    """
    # Validity
    v_valid = 1.0 if is_valid else 0.0

    # Makespan: penalize increases, slight reward for decreases
    # Score = 1 / (1 + |delta|) for increases, capped at 1 for decreases
    if makespan_delta <= 0:
        v_makespan = 1.0
    else:
        v_makespan = 1.0 / (1.0 + makespan_delta * 5)  # 20% increase → ~0.5

    # Deviation: normalize by original makespan
    if original_makespan > 0:
        norm_dev = temporal_deviation / original_makespan
        v_deviation = 1.0 / (1.0 + norm_dev)
    else:
        v_deviation = 1.0

    v_retention = constraint_retention
    v_robustness = robustness

    # Weighted sum
    score = (
        weights.get("validity", 0.3) * v_valid
        + weights.get("makespan", 0.1) * v_makespan
        + weights.get("deviation", 0.2) * v_deviation
        + weights.get("retention", 0.2) * v_retention
        + weights.get("robustness", 0.2) * v_robustness
    )

    return round(score * 100, 1)