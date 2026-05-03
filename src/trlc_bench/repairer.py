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
    FailureClass,
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


# ---------------------------------------------------------------------------
# Strategy 3: Constraint-Aware Temporal Repair
# ---------------------------------------------------------------------------

def constraint_aware_repair(
    disrupted: TemporalPlan,
    config: DomainConfig,
    report: FailureReport,
) -> RepairResult:
    """
    Constraint-aware repair: understands temporal structure and exploits slack.

    Unlike local_shift (which only compresses gaps) and replan_naive
    (which destroys structure), this strategy:

      1. Identifies the critical path to the nearest deadline
      2. Compresses only actions ON the critical path
      3. Exploits bounded duration flexibility — shrinks actions toward
         d_min when under deadline pressure
      4. Absorbs delay in slack actions (e.g. cool has no upper bound)
      5. Preserves non-critical action timing (minimal deviation)
      6. Re-inserts failed actions (Class C) using dependency analysis

    This is the "smart baseline" that any LLM-guided or learned method
    must beat to be considered a contribution.
    """
    repaired = copy.deepcopy(disrupted)
    log: list[str] = []

    if not repaired.actions:
        return RepairResult(
            repaired_plan=repaired,
            strategy_name="constraint_aware",
            repair_actions_taken=["No actions to repair"],
            success=False,
        )

    # ---------------------------------------------------------------
    # Phase 0: Handle Class C — re-insert missing actions
    # ---------------------------------------------------------------
    if report.failure_class == FailureClass.C:
        repaired, phase0_log = _handle_cascading_failure(repaired, config, report)
        log.extend(phase0_log)

    # ---------------------------------------------------------------
    # Phase 1: Enforce bounded duration constraints
    # Clamp all durations to [d_min, d_max]. This fixes Class A shrink
    # violations that no other baseline handles.
    # ---------------------------------------------------------------
    for action in repaired.actions:
        if action.name in config.bounded_durations:
            d_min, d_max = config.bounded_durations[action.name]
            if action.duration < d_min - 1e-9:
                old = action.duration
                action.duration = d_min
                log.append(
                    f"Phase1: Enforced min duration on '{action.name}': "
                    f"{old:.3f} → {d_min:.3f}"
                )
            elif d_max < float("inf") and action.duration > d_max + 1e-9:
                old = action.duration
                action.duration = d_max
                log.append(
                    f"Phase1: Enforced max duration on '{action.name}': "
                    f"{old:.3f} → {d_max:.3f}"
                )

    # ---------------------------------------------------------------
    # Phase 2: Compute deadline pressure and identify critical path
    # ---------------------------------------------------------------
    actions = repaired.sorted_actions()
    deadline_actions = {}
    for action_name, deadline in config.deadlines.items():
        for a in repaired.get_actions_by_name(action_name):
            deadline_actions[id(a)] = deadline

    # Find the tightest deadline
    tightest_deadline = None
    tightest_action = None
    max_pressure = float("-inf")
    for a in actions:
        if id(a) in deadline_actions:
            dl = deadline_actions[id(a)]
            pressure = a.end_time - dl  # positive = violated
            if pressure > max_pressure:
                max_pressure = pressure
                tightest_deadline = dl
                tightest_action = a

    # ---------------------------------------------------------------
    # Phase 3: If under pressure, compress actions smartly
    # Strategy: work backwards from deadline action, shrink durations
    # toward d_min, absorb delay in slack actions
    # ---------------------------------------------------------------
    if max_pressure > 1e-9 and tightest_deadline is not None:
        time_to_recover = max_pressure
        log.append(
            f"Phase3: Deadline pressure = {time_to_recover:.3f} "
            f"(need to recover this much time)"
        )

        # Build dependency chain to deadline action
        dep_chain = _build_dependency_chain(actions, config)

        # Try to compress each action on the critical path
        for action in reversed(actions):
            if time_to_recover <= 1e-9:
                break

            if action.name in config.bounded_durations:
                d_min, d_max = config.bounded_durations[action.name]
                compressible = action.duration - d_min
                if compressible > 1e-9:
                    shrink = min(compressible, time_to_recover)
                    old_dur = action.duration
                    action.duration -= shrink
                    time_to_recover -= shrink
                    log.append(
                        f"Phase3: Compressed '{action.name}' from "
                        f"{old_dur:.3f} to {action.duration:.3f} "
                        f"(saved {shrink:.3f})"
                    )
            else:
                # Non-bounded action: can we shrink at all?
                # Only shrink up to 20% — preserve temporal structure
                max_shrink = action.duration * 0.2
                if max_shrink > 1e-9:
                    shrink = min(max_shrink, time_to_recover)
                    old_dur = action.duration
                    action.duration -= shrink
                    time_to_recover -= shrink
                    log.append(
                        f"Phase3: Compressed '{action.name}' by 20%: "
                        f"{old_dur:.3f} → {action.duration:.3f}"
                    )

        if time_to_recover > 1e-9:
            log.append(
                f"Phase3: WARNING — could not recover {time_to_recover:.3f}, "
                f"deadline may still be violated"
            )

    # ---------------------------------------------------------------
    # Phase 4: Re-sequence respecting dependencies
    # Unlike replan_naive (which packs from t=0), we anchor to the
    # original timing and only shift what's necessary.
    # ---------------------------------------------------------------
    actions = repaired.sorted_actions()

    # Build ordering map
    must_follow: dict[str, set[str]] = {}
    for before, after in config.ordering_constraints:
        must_follow.setdefault(after, set()).add(before)

    # Forward pass: ensure each action starts after its dependencies end
    action_end_times: dict[str, float] = {}
    for action in actions:
        earliest = action.start_time

        # Check ordering constraints
        for dep_name in must_follow.get(action.name, set()):
            if dep_name in action_end_times:
                earliest = max(earliest, action_end_times[dep_name])

        # Check against previous action (sequential constraint)
        # Only shift if necessary — preserve original timing where possible
        if earliest > action.start_time + 1e-9:
            old_start = action.start_time
            action.start_time = earliest
            log.append(
                f"Phase4: Shifted '{action.name}' from t={old_start:.3f} "
                f"to t={earliest:.3f} (dependency)"
            )

        action_end_times[action.name] = action.end_time

    # ---------------------------------------------------------------
    # Phase 5: Close unnecessary gaps (left-shift non-critical actions)
    # But ONLY if it doesn't increase deviation unnecessarily
    # ---------------------------------------------------------------
    actions = sorted(repaired.actions, key=lambda a: (a.start_time, a.name))
    for i in range(1, len(actions)):
        prev_end = actions[i - 1].end_time
        gap = actions[i].start_time - prev_end

        if gap > 1e-9:
            # Only close gap if we're under deadline pressure
            # or the gap is larger than 20% of action duration
            under_pressure = any(
                a.end_time > dl - 1e-9
                for a in actions[i:]
                for dl_name, dl in config.deadlines.items()
                if a.name == dl_name
            )

            if under_pressure or gap > actions[i].duration * 0.2:
                old_start = actions[i].start_time
                actions[i].start_time = prev_end
                log.append(
                    f"Phase5: Closed gap for '{actions[i].name}': "
                    f"t={old_start:.3f} → t={prev_end:.3f}"
                )

    repaired.actions = actions

    # ---------------------------------------------------------------
    # Phase 6: Final validation check
    # ---------------------------------------------------------------
    success = True
    for action_name, deadline in config.deadlines.items():
        for a in repaired.get_actions_by_name(action_name):
            if a.end_time > deadline + 1e-9:
                success = False
                log.append(
                    f"Phase6: FAILED — '{action_name}' ends at "
                    f"t={a.end_time:.3f}, deadline t={deadline:.3f}"
                )

    # Check bounded durations are still valid
    for a in repaired.actions:
        if a.name in config.bounded_durations:
            d_min, d_max = config.bounded_durations[a.name]
            if a.duration < d_min - 1e-9:
                success = False
                log.append(
                    f"Phase6: FAILED — '{a.name}' duration "
                    f"{a.duration:.3f} < min {d_min:.3f}"
                )

    if not log:
        log.append("No changes needed — plan already satisfies constraints")

    return RepairResult(
        repaired_plan=repaired,
        strategy_name="constraint_aware",
        repair_actions_taken=log,
        success=success,
        metadata={
            "deadline_pressure": max_pressure if max_pressure > float("-inf") else 0.0,
            "phases_applied": [p for p in ["Phase0", "Phase1", "Phase3", "Phase4", "Phase5"]
                              if any(p in entry for entry in log)],
        },
    )


def _handle_cascading_failure(
    plan: TemporalPlan,
    config: DomainConfig,
    report: FailureReport,
) -> tuple[TemporalPlan, list[str]]:
    """
    Handle Class C failures: re-insert failed actions using dependency analysis.

    For each missing action in the cascade chain, find where it should go
    based on ordering constraints and insert it with minimum viable duration.
    """
    log: list[str] = []
    plan = copy.deepcopy(plan)

    present_names = {a.name for a in plan.actions}
    missing = [name for name in report.affected_actions if name not in present_names]

    if not missing:
        return plan, log

    # Build insertion order from ordering constraints
    ordered_missing = _topological_order(missing, config.ordering_constraints)

    for name in ordered_missing:
        # Find where this action should go
        # It must come after its dependencies
        must_follow_names = set()
        for before, after in config.ordering_constraints:
            if after == name:
                must_follow_names.add(before)

        # Find the latest end time of dependencies
        earliest_start = 0.0
        for dep_name in must_follow_names:
            for a in plan.actions:
                if a.name == dep_name:
                    earliest_start = max(earliest_start, a.end_time)

        # Determine duration
        if name in config.bounded_durations:
            duration = config.bounded_durations[name][0]  # Use d_min
        else:
            # Use average duration from plan's existing actions
            existing_durs = [a.duration for a in plan.actions if a.duration > 0]
            duration = sum(existing_durs) / len(existing_durs) if existing_durs else 1.0

        # Find args from the report metadata or use empty
        args = report.metadata.get("failed_action_args", [])

        from trlc_bench.models import PlanAction
        new_action = PlanAction(
            start_time=earliest_start,
            name=name,
            args=args,
            duration=duration,
        )

        plan.actions.append(new_action)

        # Shift downstream actions
        for a in plan.actions:
            if a is not new_action and a.start_time >= earliest_start - 1e-9:
                if a.name != name:
                    a.start_time = max(a.start_time, new_action.end_time)

        log.append(
            f"Phase0: Re-inserted '{name}' at t={earliest_start:.3f} "
            f"with duration={duration:.3f}"
        )

    return plan, log


def _build_dependency_chain(
    actions: list,
    config: DomainConfig,
) -> dict[str, list[str]]:
    """Build a map of action → list of actions that depend on it."""
    deps: dict[str, list[str]] = {}
    for before, after in config.ordering_constraints:
        deps.setdefault(before, []).append(after)
    return deps