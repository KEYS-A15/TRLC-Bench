"""
Parameterized rover domain builder using unified-planning.

Generates rover temporal planning problems programmatically.
Parameters control topology, number of samples, deadline tightness,
battery capacity, and distances — enabling systematic scaling.

The domain encodes:
  - Durative navigate actions (duration = distance)
  - Collect/analyze/transmit chain with ordering
  - Comm window as a timed goal (genuinely temporal)
  - Battery depletion during navigation
  - Mutex: rover can't move and work simultaneously
"""

from __future__ import annotations

from dataclasses import dataclass, field

import unified_planning as up
from unified_planning.model import DurativeAction, Problem, Timing
from unified_planning.model.timing import StartTiming, EndTiming, Timepoint, TimepointKind
from unified_planning.shortcuts import (
    BoolType,
    GE,
    IntType,
    Minus,
    Not,
    RealType,
    UserType,
    OneshotPlanner,
)


@dataclass
class RoverProblemConfig:
    """Configuration for generating a rover problem instance."""
    name: str = "rover-p01"
    num_waypoints: int = 4
    sample_locations: list[int] = field(default_factory=lambda: [2])
    comm_waypoint: int = 3
    start_waypoint: int = 0
    distances: dict[tuple[int, int], int] | None = None
    move_costs: dict[tuple[int, int], int] | None = None
    collection_duration: int = 3
    analysis_duration: int = 4
    transmit_duration: int = 2
    initial_battery: int = 100
    deadline: float = 18.0

    def __post_init__(self):
        # Default: linear chain with distance 3 between consecutive waypoints
        if self.distances is None:
            self.distances = {}
            for i in range(self.num_waypoints - 1):
                self.distances[(i, i + 1)] = 3
                self.distances[(i + 1, i)] = 3
        if self.move_costs is None:
            self.move_costs = {k: 10 for k in self.distances}


def build_rover_problem(config: RoverProblemConfig | None = None) -> Problem:
    """
    Build a unified-planning Problem for the rover domain.

    Args:
        config: Problem parameters. If None, uses defaults (matches p01).

    Returns:
        A UP Problem ready to solve with TAMER.
    """
    if config is None:
        config = RoverProblemConfig()

    # --- Types ---
    rover_type = UserType("rover")
    waypoint_type = UserType("waypoint")
    sample_type = UserType("sample")

    # --- Fluents ---
    at = up.model.Fluent("at", BoolType(), r=rover_type, w=waypoint_type)
    connected = up.model.Fluent("connected", BoolType(), f=waypoint_type, t=waypoint_type)
    sample_at = up.model.Fluent("sample_at", BoolType(), s=sample_type, w=waypoint_type)
    sample_collected = up.model.Fluent("sample_collected", BoolType(), s=sample_type)
    sample_analyzed = up.model.Fluent("sample_analyzed", BoolType(), s=sample_type)
    data_transmitted = up.model.Fluent("data_transmitted", BoolType(), s=sample_type)
    can_analyze = up.model.Fluent("can_analyze", BoolType(), r=rover_type)
    moving = up.model.Fluent("moving", BoolType(), r=rover_type)
    working = up.model.Fluent("working", BoolType(), r=rover_type)
    battery = up.model.Fluent("battery_level", IntType(0, 200), r=rover_type)
    distance = up.model.Fluent("distance", IntType(0, 100), f=waypoint_type, t=waypoint_type)
    move_cost = up.model.Fluent("move_cost", IntType(0, 100), f=waypoint_type, t=waypoint_type)

    # --- Actions ---

    # Navigate
    navigate = DurativeAction("navigate", r=rover_type, f=waypoint_type, t=waypoint_type)
    r, f, t = navigate.parameters
    navigate.set_fixed_duration(distance(f, t))
    navigate.add_condition(StartTiming(), at(r, f))
    navigate.add_condition(StartTiming(), connected(f, t))
    navigate.add_condition(StartTiming(), GE(battery(r), move_cost(f, t)))
    navigate.add_condition(StartTiming(), Not(moving(r)))
    navigate.add_condition(StartTiming(), Not(working(r)))
    navigate.add_effect(StartTiming(), at(r, f), False)
    navigate.add_effect(StartTiming(), moving(r), True)
    navigate.add_effect(EndTiming(), at(r, t), True)
    navigate.add_effect(EndTiming(), moving(r), False)
    navigate.add_decrease_effect(EndTiming(), battery(r), move_cost(f, t))

    # Collect sample
    collect = DurativeAction("collect_sample", r=rover_type, s=sample_type, w=waypoint_type)
    r, s, w = collect.parameters
    collect.set_fixed_duration(config.collection_duration)
    collect.add_condition(StartTiming(), at(r, w))
    collect.add_condition(StartTiming(), sample_at(s, w))
    collect.add_condition(StartTiming(), Not(sample_collected(s)))
    collect.add_condition(StartTiming(), Not(working(r)))
    collect.add_condition(StartTiming(), Not(moving(r)))
    collect.add_effect(StartTiming(), working(r), True)
    collect.add_effect(EndTiming(), working(r), False)
    collect.add_effect(EndTiming(), sample_collected(s), True)

    # Analyze sample
    analyze = DurativeAction("analyze_sample", r=rover_type, s=sample_type, w=waypoint_type)
    r, s, w = analyze.parameters
    analyze.set_fixed_duration(config.analysis_duration)
    analyze.add_condition(StartTiming(), at(r, w))
    analyze.add_condition(StartTiming(), sample_collected(s))
    analyze.add_condition(StartTiming(), Not(sample_analyzed(s)))
    analyze.add_condition(StartTiming(), can_analyze(r))
    analyze.add_condition(StartTiming(), Not(working(r)))
    analyze.add_condition(StartTiming(), Not(moving(r)))
    analyze.add_effect(StartTiming(), working(r), True)
    analyze.add_effect(EndTiming(), working(r), False)
    analyze.add_effect(EndTiming(), sample_analyzed(s), True)

    # Transmit data
    transmit = DurativeAction("transmit_data", r=rover_type, s=sample_type, w=waypoint_type)
    r, s, w = transmit.parameters
    transmit.set_fixed_duration(config.transmit_duration)
    transmit.add_condition(StartTiming(), at(r, w))
    transmit.add_condition(StartTiming(), sample_analyzed(s))
    transmit.add_condition(StartTiming(), Not(data_transmitted(s)))
    transmit.add_condition(StartTiming(), Not(working(r)))
    transmit.add_condition(StartTiming(), Not(moving(r)))
    transmit.add_effect(StartTiming(), working(r), True)
    transmit.add_effect(EndTiming(), working(r), False)
    transmit.add_effect(EndTiming(), data_transmitted(s), True)

    # --- Problem ---
    problem = Problem(config.name)

    # Add fluents
    for fl in [at, connected, sample_at, sample_collected, sample_analyzed,
               data_transmitted, can_analyze, moving, working, battery,
               distance, move_cost]:
        problem.add_fluent(fl, default_initial_value=False if fl.type == BoolType() else 0)

    # Add actions
    for action in [navigate, collect, analyze, transmit]:
        problem.add_action(action)

    # --- Objects ---
    r1 = problem.add_object("r1", rover_type)

    waypoints = []
    for i in range(config.num_waypoints):
        wp = problem.add_object(f"wp{i}", waypoint_type)
        waypoints.append(wp)

    samples = []
    for i, loc in enumerate(config.sample_locations):
        s = problem.add_object(f"s{i+1}", sample_type)
        samples.append((s, loc))

    # --- Initial state ---
    problem.set_initial_value(at(r1, waypoints[config.start_waypoint]), True)
    problem.set_initial_value(can_analyze(r1), True)
    problem.set_initial_value(moving(r1), False)
    problem.set_initial_value(working(r1), False)
    problem.set_initial_value(battery(r1), config.initial_battery)

    # Connectivity and distances
    for (i, j), dist in config.distances.items():
        problem.set_initial_value(connected(waypoints[i], waypoints[j]), True)
        problem.set_initial_value(distance(waypoints[i], waypoints[j]), dist)

    for (i, j), cost in config.move_costs.items():
        problem.set_initial_value(move_cost(waypoints[i], waypoints[j]), cost)

    # Sample locations
    for s, loc in samples:
        problem.set_initial_value(sample_at(s, waypoints[loc]), True)

    # --- Goals ---
    for s, _ in samples:
        problem.add_goal(data_transmitted(s))

    # Timed goal: all transmissions must complete before deadline
    # This is the genuinely temporal constraint — a classical planner can't handle this
    deadline_timing = Timing(
        delay=config.deadline,
        timepoint=Timepoint(TimepointKind.GLOBAL_START),
    )
    for s, _ in samples:
        problem.add_timed_goal(deadline_timing, data_transmitted(s))

    return problem