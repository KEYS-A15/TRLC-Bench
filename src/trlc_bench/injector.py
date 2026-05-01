"""
Failure injector implementing the TRLCBench failure taxonomy.

Class A — Duration perturbation:
    An action's duration changes (stretch or shrink). Downstream timing shifts.
    In bounded-duration domains, shrink can violate lower bounds (novel).

Class B — Structural invalidation:
    An external constraint changes (window shrinks, deadline moves).
    The plan itself is unchanged but now violates a different world.

Class C — Cascading violation:
    An action fails mid-execution. Its effects never apply.
    All downstream actions depending on those effects become invalid.

All injectors are domain-agnostic: they operate on TemporalPlan + DomainConfig.
"""

from __future__ import annotations

import copy

from trlc_bench.models import (
    DomainConfig,
    FailureClass,
    FailureReport,
    InjectionResult,
    TemporalPlan,
)


# ---------------------------------------------------------------------------
# Class A: Duration Perturbation
# ---------------------------------------------------------------------------

def inject_duration_stretch(
    plan: TemporalPlan,
    config: DomainConfig,
    target_action: str,
    stretch_factor: float = 1.5,
    cascade_downstream: bool = True,
) -> InjectionResult:
    """
    Class A failure: an action takes longer than planned.

    The target action's duration is multiplied by stretch_factor.
    If cascade_downstream is True, all subsequent actions are shifted
    forward by the extra time (rigid cascade — no reordering).

    Args:
        plan: Original valid plan.
        config: Domain configuration.
        target_action: Name of the action to stretch.
        stretch_factor: Multiplier (>1 for stretch, <1 for shrink).
        cascade_downstream: Whether to shift later actions.

    Returns:
        InjectionResult with disrupted plan and failure report.
    """
    original = copy.deepcopy(plan)
    disrupted = copy.deepcopy(plan)

    targets = [a for a in disrupted.actions if a.name == target_action]
    if not targets:
        raise ValueError(f"Action '{target_action}' not found in plan.")

    target = targets[0]
    old_duration = target.duration
    new_duration = old_duration * stretch_factor
    time_delta = new_duration - old_duration

    target.duration = new_duration

    # Cascade: shift all actions that start at or after the target's original end
    affected = [target_action]
    if cascade_downstream and abs(time_delta) > 1e-9:
        original_end = target.start_time + old_duration
        for action in disrupted.actions:
            if action is not target and action.start_time >= original_end - 1e-9:
                action.start_time += time_delta
                if action.name not in affected:
                    affected.append(action.name)

    # Determine severity
    broken = []
    for action_name, deadline in config.deadlines.items():
        for a in disrupted.get_actions_by_name(action_name):
            if a.end_time > deadline:
                broken.append(
                    f"'{action_name}' now ends at t={a.end_time:.3f}, "
                    f"deadline is t={deadline:.3f}"
                )

    # Check bounded duration violations (Class A shrink)
    if stretch_factor < 1.0:
        for action_name, (d_min, d_max) in config.bounded_durations.items():
            if action_name == target_action and new_duration < d_min:
                broken.append(
                    f"'{action_name}' duration={new_duration:.3f} "
                    f"< minimum={d_min:.3f} (lower bound violated)"
                )

    if broken:
        severity = "high" if any("deadline" in b.lower() for b in broken) else "medium"
    else:
        severity = "low"

    direction = "stretch" if stretch_factor > 1 else "shrink"
    report = FailureReport(
        failure_class=FailureClass.A,
        failure_type=f"Duration {direction.title()} ({stretch_factor:.2f}x)",
        description=(
            f"Action '{target_action}' duration changed from "
            f"{old_duration:.3f} to {new_duration:.3f} "
            f"({direction} by {abs(time_delta):.3f}). "
            f"{'Cascaded to ' + str(len(affected)-1) + ' downstream actions.' if cascade_downstream else 'No cascade.'}"
        ),
        affected_actions=affected,
        broken_constraints=broken,
        severity=severity,
        metadata={
            "target_action": target_action,
            "old_duration": old_duration,
            "new_duration": new_duration,
            "stretch_factor": stretch_factor,
            "time_delta": time_delta,
        },
    )

    return InjectionResult(
        original_plan=original,
        disrupted_plan=disrupted,
        report=report,
    )


# ---------------------------------------------------------------------------
# Class B: Structural Invalidation
# ---------------------------------------------------------------------------

def inject_window_shrink(
    plan: TemporalPlan,
    config: DomainConfig,
    deadline_name: str,
    new_deadline: float,
) -> InjectionResult:
    """
    Class B failure: an external deadline moves earlier.

    The plan is unchanged, but the world has changed — a constraint
    that was satisfied is now violated. This models real-world events
    like an OR schedule change or a comm window closing early.

    Args:
        plan: Original valid plan.
        config: Domain configuration (will be patched).
        deadline_name: Name of the deadline to change.
        new_deadline: New (earlier) deadline time.

    Returns:
        InjectionResult with unchanged plan but modified constraint.
    """
    if deadline_name not in config.deadlines:
        raise ValueError(
            f"Deadline '{deadline_name}' not found in config. "
            f"Available: {list(config.deadlines.keys())}"
        )

    original_deadline = config.deadlines[deadline_name]
    if new_deadline >= original_deadline:
        raise ValueError(
            f"New deadline {new_deadline} must be earlier than "
            f"original {original_deadline}"
        )

    original = copy.deepcopy(plan)
    # Plan doesn't change — the world does
    disrupted = copy.deepcopy(plan)

    # Check what breaks
    broken = []
    affected = []
    for a in disrupted.get_actions_by_name(deadline_name):
        if a.end_time > new_deadline:
            broken.append(
                f"'{deadline_name}' ends at t={a.end_time:.3f} "
                f"but new deadline is t={new_deadline:.3f}"
            )
            affected.append(deadline_name)

    # Also check actions that depend on the deadline action
    for dep_name in config.cascade_dependencies.get(deadline_name, []):
        affected.append(dep_name)

    severity = "high" if broken else "low"

    # Generate PDDL patch
    problem_patch = (
        f"; === FAILURE INJECTION: Class B Window Shrink ===\n"
        f"; Deadline '{deadline_name}' moved from "
        f"t={original_deadline:.3f} to t={new_deadline:.3f}\n"
    )

    report = FailureReport(
        failure_class=FailureClass.B,
        failure_type="Window Shrink (Structural Invalidation)",
        description=(
            f"Deadline '{deadline_name}' moved from "
            f"t={original_deadline:.3f} to t={new_deadline:.3f}. "
            f"Plan is unchanged but {'now violates deadline.' if broken else 'still satisfies deadline.'}"
        ),
        affected_actions=affected,
        broken_constraints=broken,
        severity=severity,
        metadata={
            "deadline_name": deadline_name,
            "original_deadline": original_deadline,
            "new_deadline": new_deadline,
        },
    )

    return InjectionResult(
        original_plan=original,
        disrupted_plan=disrupted,
        report=report,
        problem_patch=problem_patch,
    )


# ---------------------------------------------------------------------------
# Class C: Cascading Violation
# ---------------------------------------------------------------------------

def inject_action_failure(
    plan: TemporalPlan,
    config: DomainConfig,
    failed_action: str,
    failure_point: float = 0.5,
) -> InjectionResult:
    """
    Class C failure: an action fails mid-execution.

    The action's effects never apply. All downstream actions that
    depend on those effects (from config.cascade_dependencies) are
    invalidated but remain in the plan as "broken" actions.

    Args:
        plan: Original valid plan.
        config: Domain configuration.
        failed_action: Name of the action that fails.
        failure_point: Fraction through execution when failure occurs (0-1).

    Returns:
        InjectionResult with the failed action removed and dependents marked.
    """
    original = copy.deepcopy(plan)
    disrupted = copy.deepcopy(plan)

    # Find and remove the failed action
    target_idx = None
    for i, a in enumerate(disrupted.actions):
        if a.name == failed_action:
            target_idx = i
            break

    if target_idx is None:
        raise ValueError(f"Action '{failed_action}' not found in plan.")

    failed = disrupted.actions[target_idx]
    failure_time = failed.start_time + failed.duration * failure_point

    # Remove the failed action
    disrupted.actions.pop(target_idx)

    # Identify cascade
    dependents = config.cascade_dependencies.get(failed_action, [])
    affected = [failed_action]
    broken = [
        f"'{failed_action}' failed at t={failure_time:.3f} — effects never applied"
    ]

    for dep_name in dependents:
        for a in disrupted.actions:
            if a.name == dep_name:
                broken.append(
                    f"'{dep_name}' at t={a.start_time:.3f} requires effects "
                    f"of '{failed_action}' which were never produced"
                )
                if dep_name not in affected:
                    affected.append(dep_name)

    # Recursively check deeper cascades
    for dep_name in dependents:
        deeper = config.cascade_dependencies.get(dep_name, [])
        for dd in deeper:
            if dd not in affected:
                affected.append(dd)
                broken.append(
                    f"'{dd}' transitively depends on '{failed_action}' via '{dep_name}'"
                )

    severity = "catastrophic" if len(affected) >= 3 else "high"

    report = FailureReport(
        failure_class=FailureClass.C,
        failure_type="Mid-Execution Failure (Cascading Violation)",
        description=(
            f"Action '{failed_action}' failed at t={failure_time:.3f} "
            f"({failure_point*100:.0f}% through execution). "
            f"Effects never applied, invalidating {len(dependents)} "
            f"downstream action(s)."
        ),
        affected_actions=affected,
        broken_constraints=broken,
        severity=severity,
        metadata={
            "failed_action": failed_action,
            "failure_time": failure_time,
            "failure_point": failure_point,
            "cascade_depth": len(affected) - 1,
        },
    )

    return InjectionResult(
        original_plan=original,
        disrupted_plan=disrupted,
        report=report,
    )