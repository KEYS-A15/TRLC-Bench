"""
Plan trace exporter: saves the full repair trajectory for each experiment.

For each (injection × strategy) combination, outputs:
  1. Original valid plan
  2. Disrupted plan (after failure injection)
  3. Repaired plan (after repair strategy)
  4. Failure report
  5. Repair log
  6. Metrics scorecard

Output format: human-readable text file, one per problem instance.
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime

from trlc_bench.models import (
    DomainConfig,
    FailureReport,
    InjectionResult,
    RepairMetrics,
    RepairResult,
    TemporalPlan,
)


def _format_plan(plan: TemporalPlan, label: str) -> str:
    """Format a plan with a label header."""
    lines = [f"  [{label}] ({plan.num_actions} actions, makespan={plan.makespan:.3f})"]
    for a in plan.sorted_actions():
        lines.append(f"    {a}")
    return "\n".join(lines)


def _format_report(report: FailureReport) -> str:
    """Format a failure report."""
    lines = [
        f"  Class: {report.failure_class.name}",
        f"  Type: {report.failure_type}",
        f"  Severity: {report.severity}",
        f"  Description: {report.description}",
        f"  Affected actions: {', '.join(report.affected_actions)}",
    ]
    if report.broken_constraints:
        lines.append("  Broken constraints:")
        for bc in report.broken_constraints:
            lines.append(f"    - {bc}")
    return "\n".join(lines)


def _format_metrics(metrics: RepairMetrics) -> str:
    """Format a metrics scorecard."""
    lines = [
        f"  Valid: {'YES' if metrics.is_valid else 'NO'}",
        f"  TRLC Score: {metrics.trlc_score:.1f}",
        f"  Makespan: {metrics.makespan_original:.3f} -> {metrics.makespan_repaired:.3f} ({metrics.makespan_delta:+.1%})",
        f"  Temporal Deviation: {metrics.temporal_deviation:.2f}",
        f"  Action Count Delta: {metrics.action_count_delta:+d}",
        f"  Constraint Retention: {metrics.constraint_retention:.1%}",
        f"  Slack: {metrics.slack:.2f}",
        f"  Robustness: {metrics.robustness:.2f}",
    ]
    return "\n".join(lines)


def export_trace(
    output_path: str | Path,
    domain_name: str,
    problem_name: str,
    original_plan: TemporalPlan,
    injections: dict[str, InjectionResult],
    repairs: dict[str, dict[str, RepairResult]],
    metrics: dict[str, dict[str, RepairMetrics]],
) -> None:
    """
    Export full repair traces to a human-readable text file.

    Args:
        output_path: Path to write the trace file.
        domain_name: Domain name for header.
        problem_name: Problem name for header.
        original_plan: The original valid plan.
        injections: Dict of {injection_name: InjectionResult}.
        repairs: Dict of {injection_name: {strategy_name: RepairResult}}.
        metrics: Dict of {injection_name: {strategy_name: RepairMetrics}}.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "=" * 70,
        f"TRLCBench Plan Trace",
        f"Domain: {domain_name}",
        f"Problem: {problem_name}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 70,
        "",
        "ORIGINAL VALID PLAN",
        "-" * 40,
        _format_plan(original_plan, "Original"),
        "",
    ]

    for inj_name, inj_result in injections.items():
        lines.extend([
            "=" * 70,
            f"INJECTION: {inj_name}",
            "=" * 70,
            "",
            "Failure Report:",
            _format_report(inj_result.report),
            "",
            "Disrupted Plan:",
            _format_plan(inj_result.disrupted_plan, "Disrupted"),
            "",
        ])

        if inj_name in repairs:
            for strat_name, repair_result in repairs[inj_name].items():
                m = metrics.get(inj_name, {}).get(strat_name)

                lines.extend([
                    "-" * 40,
                    f"STRATEGY: {strat_name}",
                    "-" * 40,
                    "",
                    "Repair Log:",
                ])
                for action in repair_result.repair_actions_taken:
                    lines.append(f"  > {action}")

                lines.extend([
                    "",
                    "Repaired Plan:",
                    _format_plan(repair_result.repaired_plan, f"Repaired ({strat_name})"),
                    "",
                ])

                if m:
                    lines.extend([
                        "Metrics:",
                        _format_metrics(m),
                        "",
                    ])

    output_path.write_text("\n".join(lines), encoding="utf-8")