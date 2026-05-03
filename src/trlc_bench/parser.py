"""
Plan parser and domain config loader.

Parses the standard PDDL plan format:
    <start_time>: (<action_name> <arg1> ... <argN>) [<duration>]

Also loads domain configuration from YAML files.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from trlc_bench.models import (
    DomainConfig,
    PlanAction,
    TemporalPlan,
)


# ---------------------------------------------------------------------------
# PDDL plan parsing
# ---------------------------------------------------------------------------

# Matches: "0.000: (navigate r1 wp0 wp1) [3.000]"
_PLAN_LINE_RE = re.compile(
    r"^\s*"
    r"(?P<start>[0-9]+(?:\.[0-9]+)?)"   # start time
    r"\s*:\s*"
    r"\((?P<body>[^)]+)\)"               # action body
    r"\s*\[(?P<dur>[0-9]+(?:\.[0-9]+)?)\]"  # duration
    r"\s*$"
)


def parse_plan_line(line: str) -> PlanAction | None:
    """Parse a single PDDL plan line. Returns None for comments/blanks."""
    stripped = line.strip()
    if not stripped or stripped.startswith(";"):
        return None

    m = _PLAN_LINE_RE.match(stripped)
    if m is None:
        return None

    start = float(m.group("start"))
    body_parts = m.group("body").split()
    action_name = body_parts[0]
    args = body_parts[1:]
    duration = float(m.group("dur"))

    return PlanAction(
        start_time=start,
        name=action_name,
        args=args,
        duration=duration,
    )


def parse_plan(
    text: str,
    domain: str = "",
    problem: str = "",
) -> TemporalPlan:
    """
    Parse a complete PDDL plan from text.

    Args:
        text: Raw plan file content.
        domain: Domain name (metadata).
        problem: Problem name (metadata).

    Returns:
        TemporalPlan with parsed actions sorted by start time.
    """
    actions: list[PlanAction] = []

    for line in text.splitlines():
        action = parse_plan_line(line)
        if action is not None:
            actions.append(action)

    actions.sort(key=lambda a: (a.start_time, a.name))

    return TemporalPlan(actions=actions, domain=domain, problem=problem)


def parse_plan_file(
    path: str | Path,
    domain: str = "",
    problem: str = "",
) -> TemporalPlan:
    """Parse a plan from a file path."""
    path = Path(path)
    text = path.read_text()
    if not domain:
        domain = path.stem
    return parse_plan(text, domain=domain, problem=problem)


# ---------------------------------------------------------------------------
# Domain config loading (YAML)
# ---------------------------------------------------------------------------

def load_domain_config(path: str | Path) -> DomainConfig:
    """
    Load a domain configuration from YAML.

    The config file defines all domain-specific knowledge:
    deadlines, ordering constraints, mutex sets, bounded durations,
    cascade dependencies, and ergodicity properties.
    """
    path = Path(path)
    with open(path) as f:
        raw = yaml.safe_load(f)

    return DomainConfig(
        domain_name=raw["domain_name"],
        ergodicity=raw.get("ergodicity", "unknown"),
        deadlines=raw.get("deadlines", {}),
        ordering_constraints=[
            tuple(pair) for pair in raw.get("ordering_constraints", [])
        ],
        mutex_actions=[
            tuple(pair) for pair in raw.get("mutex_actions", [])
        ],
        bounded_durations={
            k: tuple(v) for k, v in raw.get("bounded_durations", {}).items()
        },
        fixed_durations=raw.get("fixed_durations", {}),
        cascade_dependencies=raw.get("cascade_dependencies", {}),
        dead_end_conditions=raw.get("dead_end_conditions", []),
        recovery_options=raw.get("recovery_options", []),
        metadata=raw.get("metadata", {}),
    )