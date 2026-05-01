"""
Temporal plan repair algorithms.

Architecture: each repair strategy is a function with signature:
    (disrupted: TemporalPlan, config: DomainConfig, report: FailureReport)
        -> RepairResult

Two baselines provided:
    1. local_shift  — compress/shift actions to meet deadlines (fast, minimal change)
    2. replan_naive  — strip and re-sequence from scratch (slow, maximal change)

Additional strategies (LLM-guided, verifier-in-loop) plug in with the same signature.
"""

from __future__ import annotations

import copy

from trlc_bench.models import (
    DomainConfig,
    FailureReport,
    RepairResult,
    TemporalPlan,
)


# ---------------------------------------------------------------------------
# Strategy 1: Local Shift Repair
# ---------------------------------------------------------------------------

def local_shift_repair(
    disrupted: TemporalPlan,
    config: DomainConfig,
    report: FailureReport,
) -> RepairResult:
    """
    Minimal repair: compress gaps and shift actions left to meet deadlines.

    Strategy:
      1. Sort actions by start time.
      2. For each action, set start_time = max(predecessor_end, current_start).
      3. If an action has a bounded duration and exceeds max, clamp to max.
      4. Check if deadlines are now met.

    This is the simplest reasonable baseline. It preserves action ordering
    and identities, only adjusting timing. It cannot reorder, insert, or
    remove actions.
    """
    repaired = copy.deepcopy(disrupted)
    actions = repaired.sorted_actions()
    log: list[str] = []

    if not actions:
        return RepairResult(
            repaired_plan=repaired,
            strategy_name="local_shift",
            repair_actions_taken=["No actions to repair"],
            success=False,
        )

    # Pass 1: Close gaps between consecutive actions (left-shift)
    for i in range(1, len(actions)):
        prev_end = actions[i - 1].end_time
        if actions[i].start_time > prev_end:
            gap = actions[i].start_time - prev_end
            old_start = actions[i].start_time
            actions[i].start_time = prev_end
            log.append(
                f"Shifted '{actions[i].name}' from t={old_start:.3f} "
                f"to t={prev_end:.3f} (closed gap of {gap:.3f})"
            )

    # Pass 2: Clamp durations to bounded maximums if overflowing
    for action in actions:
        if action.name in config.bounded_durations:
            d_min, d_max = config.bounded_durations[action.name]
            if action.duration > d_max:
                old_dur = action.duration
                action.duration = d_max
                log.append(
                    f"Clamped '{action.name}' duration from "
                    f"{old_dur:.3f} to max={d_max:.3f}"
                )
            elif action.duration < d_min:
                old_dur = action.duration
                action.duration = d_min
                log.append(
                    f"Extended '{action.name}' duration from "
                    f"{old_dur:.3f} to min={d_min:.3f}"
                )

    # Pass 3: Re-cascade after duration changes
    for i in range(1, len(actions)):
        prev_end = actions[i - 1].end_time
        if actions[i].start_time < prev_end:
            actions[i].start_time = prev_end
            log.append(
                f"Re-cascaded '{actions[i].name}' to t={prev_end:.3f}"
            )

    # Check success: are all deadlines met?
    repaired.actions = actions
    success = True
    for action_name, deadline in config.deadlines.items():
        for a in repaired.get_actions_by_name(action_name):
            if a.end_time > deadline + 1e-9:
                success = False
                log.append(
                    f"FAILED: '{action_name}' ends at t={a.end_time:.3f}, "
                    f"deadline t={deadline:.3f}"
                )

    if not log:
        log.append("No changes needed — plan already satisfies constraints")

    return RepairResult(
        repaired_plan=repaired,
        strategy_name="local_shift",
        repair_actions_taken=log,
        success=success,
    )


# ---------------------------------------------------------------------------
# Strategy 2: Naive Replan (sequential re-packing)
# ---------------------------------------------------------------------------

def replan_naive(
    disrupted: TemporalPlan,
    config: DomainConfig,
    report: FailureReport,
) -> RepairResult:
    """
    Aggressive repair: resequence all actions back-to-back from t=0.

    Ignores the original timing entirely. Packs actions sequentially
    using minimum bounded durations where applicable. This is the
    "nuclear option" — it always produces a valid sequence if one exists,
    but destroys the original plan's temporal structure.

    This baseline helps validate TRLCBench metrics: it should score
    poorly on temporal_deviation and constraint_retention even when
    it produces valid plans. If it scores well, the metrics are wrong.
    """
    repaired = copy.deepcopy(disrupted)
    log: list[str] = []

    # Respect ordering constraints: topological sort by config
    ordered_names = _topological_order(
        [a.name for a in repaired.actions],
        config.ordering_constraints,
    )

    # Rebuild action list in dependency order
    name_to_actions: dict[str, list] = {}
    for a in repaired.actions:
        name_to_actions.setdefault(a.name, []).append(a)

    new_actions = []
    for name in ordered_names:
        if name in name_to_actions:
            for a in name_to_actions[name]:
                new_actions.append(a)

    # Add any actions not in ordering constraints
    seen_names = set(ordered_names)
    for a in repaired.actions:
        if a.name not in seen_names:
            new_actions.append(a)

    # Pack sequentially from t=0
    t = 0.0
    for action in new_actions:
        old_start = action.start_time
        action.start_time = t

        # Use minimum duration if bounded
        if action.name in config.bounded_durations:
            d_min, _ = config.bounded_durations[action.name]
            if action.duration < d_min:
                action.duration = d_min

        t = action.end_time
        log.append(
            f"Packed '{action.name}' at t={action.start_time:.3f} "
            f"(was t={old_start:.3f})"
        )

    repaired.actions = new_actions

    # Check deadlines
    success = True
    for action_name, deadline in config.deadlines.items():
        for a in repaired.get_actions_by_name(action_name):
            if a.end_time > deadline + 1e-9:
                success = False
                log.append(
                    f"FAILED: '{action_name}' ends at t={a.end_time:.3f}, "
                    f"deadline t={deadline:.3f}"
                )

    return RepairResult(
        repaired_plan=repaired,
        strategy_name="replan_naive",
        repair_actions_taken=log,
        success=success,
    )


def _topological_order(
    names: list[str],
    ordering: list[tuple[str, str]],
) -> list[str]:
    """Simple topological sort respecting ordering constraints."""
    name_set = set(names)
    graph: dict[str, list[str]] = {n: [] for n in name_set}
    in_degree: dict[str, int] = {n: 0 for n in name_set}

    for before, after in ordering:
        if before in name_set and after in name_set:
            graph[before].append(after)
            in_degree[after] += 1

    queue = [n for n in names if in_degree.get(n, 0) == 0]
    result = []

    while queue:
        # Stable sort: pick first alphabetically for determinism
        queue.sort()
        node = queue.pop(0)
        result.append(node)
        for neighbor in graph.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0 and neighbor not in result:
                queue.append(neighbor)

    # Add any remaining (cycle or disconnected)
    for n in names:
        if n not in result:
            result.append(n)

    # Deduplicate preserving order
    seen = set()
    deduped = []
    for n in result:
        if n not in seen:
            seen.add(n)
            deduped.append(n)

    return deduped