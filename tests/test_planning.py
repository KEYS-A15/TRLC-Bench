"""
Tests for the planning subpackage.

Split into:
  - Offline tests (plan parsing, adapter) — always run
  - Online tests (actual solver API calls) — require network, marked with @pytest.mark.online
"""

import pytest

from trlc_bench.models import PlanAction, TemporalPlan
from trlc_bench.planning.engine import (
    PlannerStatus,
    PlanningResult,
    _parse_solver_plan,
    solve_from_files,
)
from trlc_bench.planning.adapter import temporal_plan_to_pddl


# ===========================================================================
# Offline tests — plan parsing (no network required)
# ===========================================================================

class TestPlanParsing:
    def test_parse_temporal_plan(self):
        """Parse standard temporal plan format."""
        raw = """\
0.000: (navigate r1 wp0 wp1) [3.000]
3.000: (navigate r1 wp1 wp2) [3.000]
6.000: (collect-sample r1 s1 wp2) [3.000]
"""
        plan = _parse_solver_plan(raw, domain="rover", problem="p01")
        assert plan.num_actions == 3
        assert plan.actions[0].name == "navigate"
        assert plan.actions[0].args == ["r1", "wp0", "wp1"]
        assert plan.actions[0].duration == 3.0
        assert plan.makespan == 9.0

    def test_parse_classical_plan(self):
        """Parse classical format (no times/durations)."""
        raw = """\
(navigate r1 wp0 wp1)
(navigate r1 wp1 wp2)
(collect-sample r1 s1 wp2)
"""
        plan = _parse_solver_plan(raw)
        assert plan.num_actions == 3
        assert plan.actions[0].start_time == 0.0
        assert plan.actions[1].start_time == 1.0
        assert plan.actions[2].start_time == 2.0

    def test_parse_skips_comments_and_blanks(self):
        raw = """\
; this is a comment

0.000: (navigate r1 wp0 wp1) [3.000]

; another comment
3.000: (navigate r1 wp1 wp2) [3.000]
"""
        plan = _parse_solver_plan(raw)
        assert plan.num_actions == 2

    def test_parse_empty_plan(self):
        plan = _parse_solver_plan("")
        assert plan.num_actions == 0
        assert plan.makespan == 0.0

    def test_parse_with_epsilon_gaps(self):
        """TAMER-style plans have small epsilon gaps."""
        raw = """\
0.000: (navigate r1 wp0 wp1) [3.000]
3.010: (collect-sample r1 s1 wp1) [2.000]
"""
        plan = _parse_solver_plan(raw)
        assert plan.num_actions == 2
        assert abs(plan.actions[1].start_time - 3.01) < 0.001


class TestAdapter:
    def test_pddl_serialization(self):
        plan = TemporalPlan(
            actions=[
                PlanAction(0.0, "navigate", ["r1", "wp0", "wp1"], 3.0),
                PlanAction(3.0, "collect-sample", ["r1", "s1", "wp1"], 2.0),
            ],
            domain="rover",
            problem="p01",
        )
        text = temporal_plan_to_pddl(plan)
        assert "navigate" in text
        assert "Makespan: 5.000" in text
        assert "0.000:" in text


# ===========================================================================
# Online tests — actual API calls (skip if no network)
# ===========================================================================

@pytest.mark.online
class TestSolverAPI:
    def test_solve_rover_p01(self):
        result = solve_from_files(
            "domains/rover_temporal.pddl",
            "problems/rover/p01_single_sample.pddl",
        )
        print(f"Status: {result.status}, Message: {result.message}")
        if result.status == PlannerStatus.SOLVED:
            assert result.plan is not None
            assert result.plan.num_actions > 0
            print(f"Plan: {result.plan.num_actions} actions, makespan={result.plan.makespan}")
            for a in result.plan.sorted_actions():
                print(f"  {a}")
        else:
            pytest.skip(f"Solver unavailable: {result.message}")

    def test_solve_hospital_p01(self):
        result = solve_from_files(
            "domains/hospital_sterilization.pddl",
            "problems/hospital/p01_single_batch.pddl",
        )
        print(f"Status: {result.status}, Message: {result.message}")
        if result.status == PlannerStatus.SOLVED:
            assert result.plan is not None
            assert result.plan.num_actions > 0
        else:
            pytest.skip(f"Solver unavailable: {result.message}")


@pytest.mark.online
class TestPlannerPipelineIntegration:
    def test_solver_plan_through_full_pipeline(self):
        """Solve → inject → repair → score — complete pipeline."""
        from trlc_bench.injector import inject_duration_stretch
        from trlc_bench.metrics import compute_metrics
        from trlc_bench.parser import load_domain_config
        from trlc_bench.repairer import local_shift_repair

        result = solve_from_files(
            "domains/rover_temporal.pddl",
            "problems/rover/p01_single_sample.pddl",
        )

        if result.status != PlannerStatus.SOLVED:
            pytest.skip(f"Solver unavailable: {result.message}")

        plan = result.plan
        config = load_domain_config("configs/rover_p01.yaml")

        # Inject Class A
        inj = inject_duration_stretch(plan, config, "navigate", 1.5)
        assert inj.report.failure_class.name == "A"

        # Repair
        repair = local_shift_repair(inj.disrupted_plan, config, inj.report)

        # Score
        metrics = compute_metrics(plan, repair.repaired_plan, config)
        assert isinstance(metrics.trlc_score, float)
        assert 0 <= metrics.trlc_score <= 100
        print(f"TRLC Score: {metrics.trlc_score}")