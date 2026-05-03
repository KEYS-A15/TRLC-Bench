"""
TRLC_Bench test suite.

Tests follow the module dependency order:
  models → parser → validator → injector → repairer → metrics → experiment

Each test is self-contained with inline fixtures.
"""

import pytest

from trlc_bench.models import (
    DomainConfig,
    FailureClass,
    PlanAction,
    TemporalPlan,
)
from trlc_bench.parser import parse_plan, parse_plan_line
from trlc_bench.validator import validate_plan
from trlc_bench.injector import (
    inject_action_failure,
    inject_duration_stretch,
    inject_window_shrink,
)
from trlc_bench.repairer import local_shift_repair, replan_naive, constraint_aware_repair
from trlc_bench.metrics import compute_metrics


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ROVER_PLAN_TEXT = """\
; Rover p01 valid plan
0.000: (navigate r1 wp0 wp1) [3.000]
3.000: (navigate r1 wp1 wp2) [3.000]
6.000: (collect-sample r1 s1 wp2) [3.000]
9.000: (analyze-sample r1 s1 wp2) [4.000]
13.000: (navigate r1 wp2 wp3) [3.000]
16.000: (transmit-data r1 s1 wp3) [2.000]
"""


def _rover_config() -> DomainConfig:
    return DomainConfig(
        domain_name="rover-temporal",
        ergodicity="non-ergodic",
        deadlines={"transmit-data": 18.0},
        ordering_constraints=[
            ("collect-sample", "analyze-sample"),
            ("analyze-sample", "transmit-data"),
        ],
        mutex_actions=[
            ("navigate", "collect-sample"),
            ("navigate", "analyze-sample"),
            ("navigate", "transmit-data"),
        ],
        bounded_durations={},
        cascade_dependencies={
            "collect-sample": ["analyze-sample", "transmit-data"],
            "analyze-sample": ["transmit-data"],
        },
        dead_end_conditions=["Comm window closed"],
        recovery_options=[],
    )


def _hospital_config() -> DomainConfig:
    return DomainConfig(
        domain_name="hospital-sterilization",
        ergodicity="semi-ergodic",
        deadlines={"deliver": 28.0},
        ordering_constraints=[
            ("decontaminate", "wash"),
            ("wash", "sterilize"),
            ("sterilize", "cool"),
            ("cool", "pack"),
            ("pack", "deliver"),
        ],
        mutex_actions=[
            ("decontaminate", "wash"),
            ("wash", "sterilize"),
        ],
        bounded_durations={
            "decontaminate": (3.0, 8.0),
            "wash": (2.0, 6.0),
            "sterilize": (5.0, 12.0),
            "cool": (3.0, 1000.0),
            "pack": (1.0, 4.0),
        },
        cascade_dependencies={
            "decontaminate": ["wash", "sterilize", "cool", "pack", "deliver"],
            "wash": ["sterilize", "cool", "pack", "deliver"],
        },
        dead_end_conditions=["All OR windows closed"],
        recovery_options=["Reroute to OR2"],
    )


HOSPITAL_PLAN_TEXT = """\
0.000: (transfer b1 intake decontam_st) [1.000]
1.000: (decontaminate b1 decontam_st) [3.000]
4.000: (transfer b1 decontam_st wash_st) [1.000]
5.000: (wash b1 wash_st) [2.000]
7.000: (transfer b1 wash_st sterilize_st) [1.000]
8.000: (sterilize b1 sterilize_st ac1) [5.000]
13.000: (transfer b1 sterilize_st cool_st) [1.000]
14.000: (cool b1 cool_st) [3.000]
17.000: (transfer b1 cool_st pack_st) [1.000]
18.000: (pack b1 pack_st) [1.000]
19.000: (deliver b1 pack_st or1 or1_st) [2.000]
"""


# ===========================================================================
# Parser tests
# ===========================================================================

class TestParser:
    def test_parse_single_line(self):
        action = parse_plan_line("0.000: (navigate r1 wp0 wp1) [3.000]")
        assert action is not None
        assert action.start_time == 0.0
        assert action.name == "navigate"
        assert action.args == ["r1", "wp0", "wp1"]
        assert action.duration == 3.0

    def test_parse_comment_returns_none(self):
        assert parse_plan_line("; this is a comment") is None

    def test_parse_blank_returns_none(self):
        assert parse_plan_line("   ") is None

    def test_parse_full_plan(self):
        plan = parse_plan(ROVER_PLAN_TEXT, domain="rover", problem="p01")
        assert plan.num_actions == 6
        assert plan.makespan == 18.0
        assert plan.domain == "rover"

    def test_parse_hospital_plan(self):
        plan = parse_plan(HOSPITAL_PLAN_TEXT, domain="hospital", problem="p01")
        assert plan.num_actions == 11
        assert plan.makespan == 21.0

    def test_actions_sorted_by_start_time(self):
        plan = parse_plan(ROVER_PLAN_TEXT)
        times = [a.start_time for a in plan.sorted_actions()]
        assert times == sorted(times)


# ===========================================================================
# Model tests
# ===========================================================================

class TestModels:
    def test_plan_action_end_time(self):
        a = PlanAction(start_time=3.0, name="navigate", args=["r1"], duration=5.0)
        assert a.end_time == 8.0

    def test_plan_action_overlap(self):
        a = PlanAction(start_time=0, name="a", args=[], duration=5)
        b = PlanAction(start_time=3, name="b", args=[], duration=5)
        c = PlanAction(start_time=5, name="c", args=[], duration=5)
        assert a.overlaps(b)
        assert not a.overlaps(c)  # a ends exactly when c starts

    def test_temporal_plan_makespan(self):
        plan = TemporalPlan(actions=[
            PlanAction(0, "a", [], 3),
            PlanAction(3, "b", [], 5),
        ])
        assert plan.makespan == 8.0


# ===========================================================================
# Validator tests
# ===========================================================================

class TestValidator:
    def test_valid_rover_plan(self):
        plan = parse_plan(ROVER_PLAN_TEXT)
        config = _rover_config()
        result = validate_plan(plan, config)
        assert result.is_valid, f"Expected valid but got: {result}"

    def test_valid_hospital_plan(self):
        plan = parse_plan(HOSPITAL_PLAN_TEXT)
        config = _hospital_config()
        result = validate_plan(plan, config)
        assert result.is_valid, f"Expected valid but got: {result}"

    def test_deadline_violation_detected(self):
        plan = parse_plan(ROVER_PLAN_TEXT)
        config = _rover_config()
        # Shrink deadline so plan fails
        config.deadlines["transmit-data"] = 17.0
        result = validate_plan(plan, config)
        assert not result.is_valid
        assert any("DEADLINE" in v for v in result.violations)

    def test_bounded_duration_violation_detected(self):
        """Hospital domain: action shorter than d_min should fail."""
        plan = parse_plan(HOSPITAL_PLAN_TEXT)
        config = _hospital_config()
        # Manually shrink decontaminate to 1.0 (min is 3.0)
        for a in plan.actions:
            if a.name == "decontaminate":
                a.duration = 1.0
        result = validate_plan(plan, config)
        assert not result.is_valid
        assert any("BOUNDED_DURATION" in v for v in result.violations)


# ===========================================================================
# Injector tests
# ===========================================================================

class TestInjector:
    def test_class_a_stretch(self):
        plan = parse_plan(ROVER_PLAN_TEXT)
        config = _rover_config()
        result = inject_duration_stretch(plan, config, "navigate", 1.5)
        assert result.report.failure_class == FailureClass.A
        # First navigate should now have duration 4.5 instead of 3.0
        stretched = result.disrupted_plan.get_actions_by_name("navigate")[0]
        assert abs(stretched.duration - 4.5) < 1e-9

    def test_class_a_cascade(self):
        """Stretching first navigate should push all downstream actions."""
        plan = parse_plan(ROVER_PLAN_TEXT)
        config = _rover_config()
        result = inject_duration_stretch(plan, config, "navigate", 1.5)
        tx = result.disrupted_plan.get_actions_by_name("transmit-data")[0]
        # transmit should now end after 18.0
        assert tx.end_time > 18.0

    def test_class_b_window_shrink(self):
        plan = parse_plan(ROVER_PLAN_TEXT)
        config = _rover_config()
        result = inject_window_shrink(plan, config, "transmit-data", 14.0)
        assert result.report.failure_class == FailureClass.B
        assert result.report.metadata["new_deadline"] == 14.0

    def test_class_c_cascading(self):
        plan = parse_plan(ROVER_PLAN_TEXT)
        config = _rover_config()
        result = inject_action_failure(plan, config, "collect-sample")
        assert result.report.failure_class == FailureClass.C
        assert "analyze-sample" in result.report.affected_actions
        assert "transmit-data" in result.report.affected_actions

    def test_class_c_removes_failed_action(self):
        plan = parse_plan(ROVER_PLAN_TEXT)
        config = _rover_config()
        result = inject_action_failure(plan, config, "collect-sample")
        names = [a.name for a in result.disrupted_plan.actions]
        assert "collect-sample" not in names


# ===========================================================================
# Repairer tests
# ===========================================================================

class TestRepairer:
    def test_local_shift_closes_gaps(self):
        plan = parse_plan(ROVER_PLAN_TEXT)
        config = _rover_config()
        # Inject small stretch that creates a gap
        inj = inject_duration_stretch(plan, config, "navigate", 1.1)
        repair = local_shift_repair(inj.disrupted_plan, config, inj.report)
        # Should have attempted to compress
        assert len(repair.repair_actions_taken) > 0

    def test_replan_naive_resequences(self):
        plan = parse_plan(ROVER_PLAN_TEXT)
        config = _rover_config()
        inj = inject_duration_stretch(plan, config, "navigate", 1.5)
        repair = replan_naive(inj.disrupted_plan, config, inj.report)
        # Naive replan starts from t=0
        first = repair.repaired_plan.sorted_actions()[0]
        assert first.start_time == 0.0

    def test_constraint_aware_handles_class_a(self):
        """Constraint-aware should compress durations to meet deadlines."""
        plan = parse_plan(ROVER_PLAN_TEXT)
        config = _rover_config()
        inj = inject_duration_stretch(plan, config, "navigate", 1.5)
        repair = constraint_aware_repair(inj.disrupted_plan, config, inj.report)
        assert len(repair.repair_actions_taken) > 0
        assert repair.strategy_name == "constraint_aware"

    def test_constraint_aware_respects_bounded_durations(self):
        """On hospital domain, constraint-aware should enforce [d_min, d_max]."""
        plan = parse_plan(HOSPITAL_PLAN_TEXT)
        config = _hospital_config()
        # Inject shrink that violates lower bound
        inj = inject_duration_stretch(plan, config, "decontaminate", 0.5)
        repair = constraint_aware_repair(inj.disrupted_plan, config, inj.report)
        # The repaired plan should have decontaminate >= d_min
        for a in repair.repaired_plan.actions:
            if a.name == "decontaminate":
                assert a.duration >= 3.0 - 1e-9, (
                    f"decontaminate duration {a.duration} < d_min 3.0"
                )

    def test_constraint_aware_handles_class_c(self):
        """Constraint-aware should re-insert failed actions."""
        plan = parse_plan(ROVER_PLAN_TEXT)
        config = _rover_config()
        inj = inject_action_failure(plan, config, "collect-sample")
        repair = constraint_aware_repair(inj.disrupted_plan, config, inj.report)
        # Should have re-inserted collect-sample
        names = [a.name for a in repair.repaired_plan.actions]
        assert "collect-sample" in names, "Failed action should be re-inserted"

    def test_constraint_aware_beats_naive_on_deviation(self):
        """
        Key benchmark property: constraint-aware should have LOWER
        temporal deviation than naive replan, while being at least as valid.
        """
        plan = parse_plan(ROVER_PLAN_TEXT)
        config = _rover_config()
        inj = inject_duration_stretch(plan, config, "navigate", 1.3)

        repair_aware = constraint_aware_repair(inj.disrupted_plan, config, inj.report)
        repair_naive = replan_naive(inj.disrupted_plan, config, inj.report)

        m_aware = compute_metrics(plan, repair_aware.repaired_plan, config)
        m_naive = compute_metrics(plan, repair_naive.repaired_plan, config)

        assert m_aware.temporal_deviation <= m_naive.temporal_deviation, (
            f"Constraint-aware deviation ({m_aware.temporal_deviation}) should be "
            f"<= naive ({m_naive.temporal_deviation})"
        )


# ===========================================================================
# Metrics tests
# ===========================================================================

class TestMetrics:
    def test_identical_plans_score_high(self):
        plan = parse_plan(ROVER_PLAN_TEXT)
        config = _rover_config()
        metrics = compute_metrics(plan, plan, config)
        assert metrics.is_valid
        # Score is 80 not 100 because rover p01 has zero slack → robustness=0.
        # This is CORRECT: a zero-slack plan IS fragile. The metric catches it.
        assert metrics.trlc_score >= 75.0
        assert metrics.temporal_deviation == 0.0
        assert metrics.robustness == 0.0  # zero slack = zero robustness

    def test_naive_replan_scores_lower_on_deviation(self):
        """
        Key benchmark property: naive replan should produce a valid plan
        but score poorly on temporal_deviation compared to local_shift.
        If this test fails, the metrics don't discriminate — which means
        the benchmark is broken.
        """
        plan = parse_plan(ROVER_PLAN_TEXT)
        config = _rover_config()
        inj = inject_duration_stretch(plan, config, "navigate", 1.3)

        repair_local = local_shift_repair(inj.disrupted_plan, config, inj.report)
        repair_naive = replan_naive(inj.disrupted_plan, config, inj.report)

        m_local = compute_metrics(plan, repair_local.repaired_plan, config)
        m_naive = compute_metrics(plan, repair_naive.repaired_plan, config)

        # Naive should have >= deviation than local shift
        # (it resequences everything from scratch)
        assert m_naive.temporal_deviation >= m_local.temporal_deviation

    def test_invalid_plan_scores_zero_validity(self):
        plan = parse_plan(ROVER_PLAN_TEXT)
        config = _rover_config()
        # Make deadline impossible
        config.deadlines["transmit-data"] = 10.0
        metrics = compute_metrics(plan, plan, config)
        assert not metrics.is_valid


# ===========================================================================
# End-to-end integration test
# ===========================================================================

class TestEndToEnd:
    def test_full_pipeline_rover(self):
        """Complete pipeline: parse → inject → repair → validate → score."""
        plan = parse_plan(ROVER_PLAN_TEXT, domain="rover", problem="p01")
        config = _rover_config()

        # Step 1: Validate original
        assert validate_plan(plan, config).is_valid

        # Step 2: Inject Class A
        inj = inject_duration_stretch(plan, config, "navigate", 1.5)
        assert inj.report.failure_class == FailureClass.A

        # Step 3: Repair
        repair = local_shift_repair(inj.disrupted_plan, config, inj.report)

        # Step 4: Score
        metrics = compute_metrics(plan, repair.repaired_plan, config)
        assert isinstance(metrics.trlc_score, float)
        assert 0 <= metrics.trlc_score <= 100

    def test_full_pipeline_hospital(self):
        """Complete pipeline for hospital domain with bounded durations."""
        plan = parse_plan(HOSPITAL_PLAN_TEXT, domain="hospital", problem="p01")
        config = _hospital_config()

        # Validate original
        assert validate_plan(plan, config).is_valid

        # Inject Class A: stretch sterilize
        inj = inject_duration_stretch(plan, config, "sterilize", 1.5)

        # Repair
        repair = local_shift_repair(inj.disrupted_plan, config, inj.report)

        # Score
        metrics = compute_metrics(plan, repair.repaired_plan, config)
        assert isinstance(metrics.trlc_score, float)