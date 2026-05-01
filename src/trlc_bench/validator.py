"""
Structural temporal plan validator.

Validates a TemporalPlan against a DomainConfig. Domain-agnostic:
all domain-specific knowledge comes from the config, not from code.

Checks:
  1. Deadline satisfaction (actions finish before deadlines)
  2. Ordering constraints (a must end before b starts)
  3. Mutex constraints (a and b cannot overlap)
  4. Bounded duration constraints (duration ∈ [d_min, d_max])
"""

from __future__ import annotations

from dataclasses import dataclass, field

from trlc_bench.models import DomainConfig, PlanAction, TemporalPlan


@dataclass
class ValidationResult:
    """Result of validating a temporal plan."""
    is_valid: bool
    violations: list[str] = field(default_factory=list)

    def add_violation(self, msg: str) -> None:
        self.violations.append(msg)
        self.is_valid = False

    def __repr__(self) -> str:
        if self.is_valid:
            return "ValidationResult(VALID)"
        return (
            f"ValidationResult(INVALID, {len(self.violations)} violations):\n"
            + "\n".join(f"  - {v}" for v in self.violations)
        )


def validate_plan(plan: TemporalPlan, config: DomainConfig) -> ValidationResult:
    """
    Validate a temporal plan against domain constraints.

    This is the structural validator. It checks timing constraints
    that can be verified from the plan alone, without simulating
    the full PDDL state. For authoritative validation, use an
    external tool like VAL.

    Args:
        plan: The temporal plan to validate.
        config: Domain configuration with constraint definitions.

    Returns:
        ValidationResult with any violations found.
    """
    result = ValidationResult(is_valid=True)

    _check_deadlines(plan, config, result)
    _check_ordering(plan, config, result)
    _check_mutex(plan, config, result)
    _check_bounded_durations(plan, config, result)

    return result


# ---------------------------------------------------------------------------
# Individual constraint checks
# ---------------------------------------------------------------------------

def _check_deadlines(
    plan: TemporalPlan, config: DomainConfig, result: ValidationResult
) -> None:
    """Check that actions with deadline constraints finish in time."""
    for action_name, deadline in config.deadlines.items():
        matching = plan.get_actions_by_name(action_name)
        for action in matching:
            if action.end_time > deadline:
                result.add_violation(
                    f"DEADLINE: '{action_name}' ends at t={action.end_time:.3f} "
                    f"but deadline is t={deadline:.3f} "
                    f"(missed by {action.end_time - deadline:.3f})"
                )


def _check_ordering(
    plan: TemporalPlan, config: DomainConfig, result: ValidationResult
) -> None:
    """Check that ordering constraints (a before b) are satisfied."""
    for before_name, after_name in config.ordering_constraints:
        befores = plan.get_actions_by_name(before_name)
        afters = plan.get_actions_by_name(after_name)

        if not befores and afters:
            result.add_violation(
                f"ORDERING: '{after_name}' present but prerequisite "
                f"'{before_name}' is missing from plan"
            )
            continue

        # For each 'after' action, at least one 'before' must have ended first
        for after_action in afters:
            if not any(b.end_time <= after_action.start_time for b in befores):
                best_end = min(b.end_time for b in befores) if befores else float("inf")
                result.add_violation(
                    f"ORDERING: '{after_name}' starts at t={after_action.start_time:.3f} "
                    f"but '{before_name}' doesn't end until t={best_end:.3f}"
                )


def _check_mutex(
    plan: TemporalPlan, config: DomainConfig, result: ValidationResult
) -> None:
    """Check that mutually exclusive actions don't overlap."""
    for name_a, name_b in config.mutex_actions:
        actions_a = plan.get_actions_by_name(name_a)
        actions_b = plan.get_actions_by_name(name_b)

        for a in actions_a:
            for b in actions_b:
                if a.overlaps(b):
                    result.add_violation(
                        f"MUTEX: '{name_a}' [{a.start_time:.3f},{a.end_time:.3f}] "
                        f"overlaps '{name_b}' [{b.start_time:.3f},{b.end_time:.3f}]"
                    )


def _check_bounded_durations(
    plan: TemporalPlan, config: DomainConfig, result: ValidationResult
) -> None:
    """Check that actions respect bounded duration constraints [d_min, d_max]."""
    for action_name, (d_min, d_max) in config.bounded_durations.items():
        matching = plan.get_actions_by_name(action_name)
        for action in matching:
            if action.duration < d_min - 1e-9:
                result.add_violation(
                    f"BOUNDED_DURATION: '{action_name}' duration={action.duration:.3f} "
                    f"< minimum={d_min:.3f} (too short — constraint violated)"
                )
            if d_max < float("inf") and action.duration > d_max + 1e-9:
                result.add_violation(
                    f"BOUNDED_DURATION: '{action_name}' duration={action.duration:.3f} "
                    f"> maximum={d_max:.3f} (too long — constraint violated)"
                )