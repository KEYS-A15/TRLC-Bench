"""
Plan adapter: serialization utilities for TRLCBench TemporalPlan.

Provides PDDL plan format serialization. The solver.planning.domains
engine handles parsing directly, so no UP conversion is needed.
"""

from __future__ import annotations

from trlc_bench.models import TemporalPlan


def temporal_plan_to_pddl(plan: TemporalPlan) -> str:
    """
    Serialize a TemporalPlan to standard PDDL plan format.

    Format per line: <start>: (<action> <arg1> ... <argN>) [<duration>]
    """
    lines = [
        f"; TRLCBench plan for {plan.domain}/{plan.problem}",
        f"; Makespan: {plan.makespan:.3f}",
        f"; Actions: {plan.num_actions}",
        "",
    ]

    for action in plan.sorted_actions():
        args_str = " ".join(action.args)
        lines.append(
            f"{action.start_time:.3f}: ({action.name} {args_str}) [{action.duration:.3f}]"
        )

    return "\n".join(lines)