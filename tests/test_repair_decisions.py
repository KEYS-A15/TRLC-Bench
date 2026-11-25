from trlc_bench.experiment import run_single_experiment
from trlc_bench.injector import inject_window_shrink
from trlc_bench.parser import load_domain_config, parse_plan_file
from trlc_bench.repairer import local_shift_repair, rule_based_repair


def test_window_shrink_reaches_repair_and_scoring():
    plan = parse_plan_file("plans/rover/p02_valid.plan")
    config = load_domain_config("configs/rover_p02.yaml")
    incident = inject_window_shrink(plan, config, "transmit-data", 22.5)

    repair, metrics = run_single_experiment(plan, config, incident, local_shift_repair)

    assert not repair.success
    assert not metrics.is_valid
    assert metrics.slack < 0
    assert config.deadlines["transmit-data"] == 30


def test_policy_keeps_a_plan_that_already_passes():
    plan = parse_plan_file("plans/hospital/p01_valid.plan")
    config = load_domain_config("configs/hospital_p01.yaml")
    incident = inject_window_shrink(plan, config, "deliver", 24)

    repair, metrics = run_single_experiment(
        plan, config, incident, rule_based_repair
    )

    assert metrics.is_valid
    assert metrics.temporal_deviation == 0
    assert repair.metadata.get("selected_strategy") == "keep"


def test_policy_rejects_candidates_that_miss_the_new_deadline():
    plan = parse_plan_file("plans/rover/p02_valid.plan")
    config = load_domain_config("configs/rover_p02.yaml")
    incident = inject_window_shrink(plan, config, "transmit-data", 1)

    repair, metrics = run_single_experiment(
        plan, config, incident, rule_based_repair
    )

    assert not repair.success
    assert not metrics.is_valid
    assert repair.metadata.get("selected_strategy") is None


def test_policy_selects_local_shift_when_removing_gaps_is_enough():
    plan = parse_plan_file("plans/hospital/p01_valid.plan")
    config = load_domain_config("configs/hospital_p01.yaml")
    incident = inject_window_shrink(plan, config, "deliver", 21.005)

    repair, metrics = run_single_experiment(plan, config, incident, rule_based_repair)

    assert repair.success
    assert metrics.is_valid
    assert repair.metadata["selected_strategy"] == "local_shift"
