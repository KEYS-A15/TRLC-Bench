"""
TRLCBench CLI — run experiments from the command line.

Usage:
    trlcbench run --config configs/rover_p01.yaml --plan plans/rover/p01_valid.plan
    trlcbench validate --config configs/rover_p01.yaml --plan plans/rover/p01_valid.plan
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from trlc_bench.experiment import print_results_table, run_experiment_matrix, run_single_experiment
from trlc_bench.injector import (
    inject_action_failure,
    inject_duration_stretch,
    inject_window_shrink,
)
from trlc_bench.metrics import compute_metrics
from trlc_bench.parser import load_domain_config, parse_plan_file
from trlc_bench.repairer import local_shift_repair, replan_naive, constraint_aware_repair
from trlc_bench.repairer import rule_based_repair
from trlc_bench.trace_exporter import export_trace
from trlc_bench.validator import validate_plan
from trlc_bench.models import RepairResult
from trlc_bench.llm_repair import llm_repair


def cmd_validate(args: argparse.Namespace) -> None:
    """Validate a plan against a domain config."""
    config = load_domain_config(args.config)
    plan = parse_plan_file(args.plan, domain=config.domain_name)

    print(f"Domain:  {config.domain_name}")
    print(f"Plan:    {args.plan} ({plan.num_actions} actions, makespan={plan.makespan:.3f})")
    print()

    result = validate_plan(plan, config)
    print(result)


def cmd_run(args: argparse.Namespace) -> None:
    """Run full experiment matrix: all injections × all strategies."""
    config = load_domain_config(args.config)
    plan = parse_plan_file(args.plan, domain=config.domain_name)

    print(f"Domain:  {config.domain_name} ({config.ergodicity})")
    print(f"Plan:    {args.plan} ({plan.num_actions} actions, makespan={plan.makespan:.3f})")
    print()

    # Build injection set
    injections = {}

    # Class A: duration stretch on first navigate (or first action)
    first_action = plan.sorted_actions()[0] if plan.actions else None
    if first_action:
        injections["A_stretch_1.5x"] = inject_duration_stretch(
            plan, config, first_action.name, stretch_factor=1.5
        )
        injections["A_stretch_2.0x"] = inject_duration_stretch(
            plan, config, first_action.name, stretch_factor=2.0
        )

    # Class B: window shrink (if deadlines exist)
    for dl_name, dl_time in config.deadlines.items():
        # Shrink by 25%
        new_dl = dl_time * 0.75
        injections[f"B_shrink_{dl_name}"] = inject_window_shrink(
            plan, config, dl_name, new_deadline=new_dl
        )

    # Class C: cascading failure on middle action
    mid_idx = len(plan.actions) // 2
    if plan.actions:
        mid_action = plan.sorted_actions()[mid_idx]
        injections[f"C_fail_{mid_action.name}"] = inject_action_failure(
            plan, config, mid_action.name, failure_point=0.5
        )

    # Repair strategies
    strategies = {
        "local_shift": local_shift_repair,
        "replan_naive": replan_naive,
        "constraint_aware": constraint_aware_repair,
        "rule_based": rule_based_repair,
        "llm_repair": llm_repair,
    }

    # Run matrix
    df = run_experiment_matrix(plan, config, injections, strategies)

    # Also collect individual repairs and metrics for trace export
    all_repairs: dict[str, dict[str, RepairResult]] = {}
    all_metrics: dict[str, dict[str, object]] = {}
    for inj_name, inj_result in injections.items():
        all_repairs[inj_name] = {}
        all_metrics[inj_name] = {}
        for strat_name, repair_fn in strategies.items():
            repair, met = run_single_experiment(plan, config, inj_result, repair_fn)
            all_repairs[inj_name][strat_name] = repair
            all_metrics[inj_name][strat_name] = met

    # Display
    print_results_table(df)

    # Save results
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output, index=False)
        print(f"\nResults saved to {output}")

    # Save trace
    if args.trace:
        trace_path = Path(args.trace)
        export_trace(
            output_path=trace_path,
            domain_name=config.domain_name,
            problem_name=args.plan,
            original_plan=plan,
            injections=injections,
            repairs=all_repairs,
            metrics=all_metrics,
        )
        print(f"Trace saved to {trace_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="trlcbench",
        description="TRLCBench: Temporal Plan Repair Benchmark",
    )
    subparsers = parser.add_subparsers(dest="command")

    # validate
    p_val = subparsers.add_parser("validate", help="Validate a plan")
    p_val.add_argument("--config", required=True, help="Domain config YAML")
    p_val.add_argument("--plan", required=True, help="Plan file")

    # run
    p_run = subparsers.add_parser("run", help="Run experiment matrix")
    p_run.add_argument("--config", required=True, help="Domain config YAML")
    p_run.add_argument("--plan", required=True, help="Plan file")
    p_run.add_argument("--output", help="Output CSV path")
    p_run.add_argument("--trace", help="Output plan trace file path")

    args = parser.parse_args()

    if args.command == "validate":
        cmd_validate(args)
    elif args.command == "run":
        cmd_run(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
