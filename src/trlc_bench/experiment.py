"""
Experiment runner: ties the full pipeline together.

    Plan → Inject → Repair → Validate → Score

Produces a results table (DataFrame) comparing repair strategies
across failure types for a given domain/problem.
"""

from __future__ import annotations

from typing import Callable

import pandas as pd

from trlc_bench.models import (
    DomainConfig,
    FailureReport,
    InjectionResult,
    RepairMetrics,
    RepairResult,
    TemporalPlan,
)
from trlc_bench.metrics import compute_metrics


# Type alias for repair strategy functions
RepairFn = Callable[
    [TemporalPlan, DomainConfig, FailureReport],
    RepairResult,
]

# Type alias for injection functions
InjectFn = Callable[..., InjectionResult]


def run_single_experiment(
    plan: TemporalPlan,
    config: DomainConfig,
    injection_result: InjectionResult,
    repair_fn: RepairFn,
) -> tuple[RepairResult, RepairMetrics]:
    """
    Run a single inject → repair → score cycle.

    Args:
        plan: Original valid plan (for metric comparison).
        config: Domain configuration.
        injection_result: Pre-computed injection (disrupted plan + report).
        repair_fn: Repair strategy to apply.

    Returns:
        Tuple of (RepairResult, RepairMetrics).
    """
    config = injection_result.config_override or config
    repair = repair_fn(
        injection_result.disrupted_plan,
        config,
        injection_result.report,
    )

    metrics = compute_metrics(
        original=plan,
        repaired=repair.repaired_plan,
        config=config,
    )

    return repair, metrics


def run_experiment_matrix(
    plan: TemporalPlan,
    config: DomainConfig,
    injections: dict[str, InjectionResult],
    strategies: dict[str, RepairFn],
) -> pd.DataFrame:
    """
    Run all combinations of injections × repair strategies.

    Args:
        plan: Original valid plan.
        config: Domain configuration.
        injections: Dict of {injection_name: InjectionResult}.
        strategies: Dict of {strategy_name: repair_function}.

    Returns:
        DataFrame with one row per (injection, strategy) combination.
    """
    rows = []

    for inj_name, inj_result in injections.items():
        for strat_name, repair_fn in strategies.items():
            repair, metrics = run_single_experiment(
                plan=plan,
                config=config,
                injection_result=inj_result,
                repair_fn=repair_fn,
            )

            rows.append({
                "domain": config.domain_name,
                "injection": inj_name,
                "failure_class": inj_result.report.failure_class.name,
                "severity": inj_result.report.severity,
                "strategy": strat_name,
                "valid": metrics.is_valid,
                "makespan_delta": metrics.makespan_delta,
                "temporal_deviation": metrics.temporal_deviation,
                "action_count_delta": metrics.action_count_delta,
                "constraint_retention": metrics.constraint_retention,
                "slack": metrics.slack,
                "robustness": metrics.robustness,
                "trlc_score": metrics.trlc_score,
                "repair_success": repair.success,
            })

    return pd.DataFrame(rows)


def print_results_table(df: pd.DataFrame) -> None:
    """Pretty-print results table using rich."""
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(
            title="TRLCBench Results",
            show_lines=True,
        )

        table.add_column("Injection", style="cyan")
        table.add_column("Class", style="magenta")
        table.add_column("Strategy", style="green")
        table.add_column("Valid", style="bold")
        table.add_column("TRLC Score", style="bold yellow")
        table.add_column("Slack", style="blue")
        table.add_column("Deviation", style="red")
        table.add_column("Retention", style="green")

        for _, row in df.iterrows():
            valid_str = "✓" if row["valid"] else "✗"
            valid_style = "green" if row["valid"] else "red"
            table.add_row(
                str(row["injection"]),
                str(row["failure_class"]),
                str(row["strategy"]),
                f"[{valid_style}]{valid_str}[/{valid_style}]",
                f"{row['trlc_score']:.1f}",
                f"{row['slack']:.2f}",
                f"{row['temporal_deviation']:.2f}",
                f"{row['constraint_retention']:.1%}",
            )

        console.print(table)

    except ImportError:
        print(df.to_string(index=False))
