"""
Planning engine: solve temporal problems via solver.planning.domains HTTP API.

No local planner installation required. Sends raw PDDL text to the
planning.domains solver and parses the returned plan.

Limitations:
  - Rate-limited: 1 request per ~20 seconds
  - Educational use only (per their terms)
  - Requires internet connection

For production/batch runs, install a local planner (OPTIC, ENHSP)
and swap this module.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

import requests

from trlc_bench.models import PlanAction, TemporalPlan


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class PlannerStatus(Enum):
    SOLVED = auto()
    UNSOLVABLE = auto()
    TIMEOUT = auto()
    ERROR = auto()


@dataclass
class PlanningResult:
    """Result from the planning engine."""
    status: PlannerStatus
    plan: TemporalPlan | None
    planner_name: str
    solve_time_ms: float
    message: str = ""
    raw_plan_text: str = ""


# ---------------------------------------------------------------------------
# API endpoint
# ---------------------------------------------------------------------------

SOLVER_URL = "http://solver.planning.domains/solve"


def solve_from_pddl(
    domain_text: str,
    problem_text: str,
    domain_name: str = "",
    problem_name: str = "",
    timeout_sec: float = 60.0,
) -> PlanningResult:
    """
    Solve a temporal planning problem via solver.planning.domains.

    Args:
        domain_text: Raw PDDL domain file content.
        problem_text: Raw PDDL problem file content.
        domain_name: Domain name for metadata.
        problem_name: Problem name for metadata.
        timeout_sec: HTTP timeout in seconds.

    Returns:
        PlanningResult with parsed TemporalPlan (if solved).
    """
    start = time.perf_counter()

    try:
        resp = requests.post(
            SOLVER_URL,
            json={"domain": domain_text, "problem": problem_text},
            timeout=timeout_sec,
        )
        elapsed = (time.perf_counter() - start) * 1000

        if resp.status_code != 200:
            return PlanningResult(
                status=PlannerStatus.ERROR,
                plan=None,
                planner_name="solver.planning.domains",
                solve_time_ms=elapsed,
                message=f"HTTP {resp.status_code}: {resp.text[:200]}",
            )

        data = resp.json()

        if data.get("status") == "ok":
            result = data.get("result", {})
            raw_plan = result.get("plan", "")

            # Parse the plan text into a TemporalPlan
            plan = _parse_solver_plan(
                raw_plan, domain=domain_name, problem=problem_name
            )

            return PlanningResult(
                status=PlannerStatus.SOLVED,
                plan=plan,
                planner_name="solver.planning.domains",
                solve_time_ms=elapsed,
                raw_plan_text=raw_plan,
            )
        else:
            # Check if unsolvable vs error
            result = data.get("result", {})
            error_msg = str(result.get("error", data.get("result", "")))

            if "unsolvable" in error_msg.lower() or "no plan" in error_msg.lower():
                return PlanningResult(
                    status=PlannerStatus.UNSOLVABLE,
                    plan=None,
                    planner_name="solver.planning.domains",
                    solve_time_ms=elapsed,
                    message=error_msg[:500],
                )
            else:
                return PlanningResult(
                    status=PlannerStatus.ERROR,
                    plan=None,
                    planner_name="solver.planning.domains",
                    solve_time_ms=elapsed,
                    message=error_msg[:500],
                )

    except requests.Timeout:
        elapsed = (time.perf_counter() - start) * 1000
        return PlanningResult(
            status=PlannerStatus.TIMEOUT,
            plan=None,
            planner_name="solver.planning.domains",
            solve_time_ms=elapsed,
            message=f"Request timed out after {timeout_sec}s",
        )
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        return PlanningResult(
            status=PlannerStatus.ERROR,
            plan=None,
            planner_name="solver.planning.domains",
            solve_time_ms=elapsed,
            message=str(e),
        )


def solve_from_files(
    domain_path: str | Path,
    problem_path: str | Path,
    timeout_sec: float = 60.0,
) -> PlanningResult:
    """
    Convenience: solve from PDDL file paths.

    Args:
        domain_path: Path to PDDL domain file.
        problem_path: Path to PDDL problem file.
        timeout_sec: HTTP timeout.

    Returns:
        PlanningResult with parsed TemporalPlan (if solved).
    """
    domain_path = Path(domain_path)
    problem_path = Path(problem_path)

    domain_text = domain_path.read_text(encoding="utf-8")
    problem_text = problem_path.read_text(encoding="utf-8")

    domain_name = domain_path.stem
    problem_name = problem_path.stem

    return solve_from_pddl(
        domain_text=domain_text,
        problem_text=problem_text,
        domain_name=domain_name,
        problem_name=problem_name,
        timeout_sec=timeout_sec,
    )


# ---------------------------------------------------------------------------
# Plan parsing
# ---------------------------------------------------------------------------

# Matches temporal plan format: "0.000: (action arg1 arg2) [3.000]"
_TEMPORAL_RE = re.compile(
    r"^\s*(?P<start>[0-9]+(?:\.[0-9]+)?)"
    r"\s*:\s*"
    r"\((?P<body>[^)]+)\)"
    r"\s*\[(?P<dur>[0-9]+(?:\.[0-9]+)?)\]"
)

# Matches classical plan format: "(action arg1 arg2)" — no times/durations
_CLASSICAL_RE = re.compile(
    r"^\s*\((?P<body>[^)]+)\)\s*$"
)


def _parse_solver_plan(
    raw_plan: str,
    domain: str = "",
    problem: str = "",
) -> TemporalPlan:
    """
    Parse a plan from the solver API response.

    Handles both temporal format (with start times and durations)
    and classical format (just action names — we assign sequential times).
    """
    actions: list[PlanAction] = []

    for line in raw_plan.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue

        # Try temporal format first
        m = _TEMPORAL_RE.match(stripped)
        if m:
            start = float(m.group("start"))
            parts = m.group("body").split()
            name = parts[0]
            args = parts[1:]
            dur = float(m.group("dur"))
            actions.append(PlanAction(
                start_time=start, name=name, args=args, duration=dur
            ))
            continue

        # Fall back to classical format
        m = _CLASSICAL_RE.match(stripped)
        if m:
            parts = m.group("body").split()
            name = parts[0]
            args = parts[1:]
            # Assign sequential times with duration 1
            t = float(len(actions))
            actions.append(PlanAction(
                start_time=t, name=name, args=args, duration=1.0
            ))

    actions.sort(key=lambda a: (a.start_time, a.name))

    return TemporalPlan(actions=actions, domain=domain, problem=problem)