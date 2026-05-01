"""
Data models for TRLCBench.

Design rules:
  - No domain-specific logic lives here.
  - Every other module imports from here; this module imports from nothing internal.
  - Immutable where possible (frozen dataclasses).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any






@dataclass
class PlanAction:
    """A single durative action in a temporal plan."""
    start_time: float
    name: str
    args: list[str]
    duration: float

    @property
    def end_time(self) -> float:
        return self.start_time + self.duration

    def overlaps(self, other: PlanAction) -> bool:
        """True if this action's execution interval overlaps with other's."""
        return self.start_time < other.end_time and other.start_time < self.end_time

    def __repr__(self) -> str:
        args_str = " ".join(self.args)
        return (
            f"{self.start_time:.3f}: ({self.name} {args_str}) [{self.duration:.3f}]"
        )


@dataclass
class TemporalPlan:
    """A complete temporal plan: ordered list of durative actions + metadata."""
    actions: list[PlanAction]
    domain: str = ""
    problem: str = ""

    @property
    def makespan(self) -> float:
        if not self.actions:
            return 0.0
        return max(a.end_time for a in self.actions)

    @property
    def num_actions(self) -> int:
        return len(self.actions)

    def get_actions_by_name(self, name: str) -> list[PlanAction]:
        return [a for a in self.actions if a.name == name]

    def sorted_actions(self) -> list[PlanAction]:
        return sorted(self.actions, key=lambda a: (a.start_time, a.name))

    def __repr__(self) -> str:
        lines = [f"TemporalPlan(domain={self.domain}, problem={self.problem}, "
                 f"actions={self.num_actions}, makespan={self.makespan:.3f})"]
        for a in self.sorted_actions():
            lines.append(f"  {a}")
        return "\n".join(lines)






class FailureClass(Enum):
    """The three failure classes in TRLCBench's taxonomy."""
    A = auto()  
    B = auto()  
    C = auto()  


@dataclass
class FailureReport:
    """Complete description of an injected failure."""
    failure_class: FailureClass
    failure_type: str           
    description: str            
    affected_actions: list[str] 
    broken_constraints: list[str]
    severity: str               
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class InjectionResult:
    """Output of the failure injector."""
    original_plan: TemporalPlan
    disrupted_plan: TemporalPlan
    report: FailureReport
    problem_patch: str = ""     






@dataclass
class RepairResult:
    """Output of a repair algorithm."""
    repaired_plan: TemporalPlan
    strategy_name: str
    repair_actions_taken: list[str]  
    success: bool                    
    metadata: dict[str, Any] = field(default_factory=dict)






@dataclass
class RepairMetrics:
    """Full TRLCBench scorecard for a single repair attempt."""
    is_valid: bool
    makespan_original: float
    makespan_repaired: float
    makespan_delta: float           
    temporal_deviation: float       
    action_count_delta: int         
    constraint_retention: float     
    slack: float                    
    robustness: float               
    trlc_score: float               

    def summary_dict(self) -> dict[str, Any]:
        return {
            "valid": self.is_valid,
            "makespan_delta": f"{self.makespan_delta:+.1%}",
            "temporal_deviation": f"{self.temporal_deviation:.2f}",
            "action_count_delta": self.action_count_delta,
            "constraint_retention": f"{self.constraint_retention:.1%}",
            "slack": f"{self.slack:.2f}",
            "robustness": f"{self.robustness:.2f}",
            "trlc_score": f"{self.trlc_score:.1f}",
        }






@dataclass
class TemporalConstraint:
    """A single temporal constraint from the domain config."""
    name: str
    constraint_type: str       
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class DomainConfig:
    """
    Domain-specific configuration loaded from YAML.
    
    This is where all domain knowledge lives. The Python code is
    domain-agnostic — it reads this config to know what to validate,
    what to inject, and what to measure.
    """
    domain_name: str
    ergodicity: str                          
    deadlines: dict[str, float]              
    ordering_constraints: list[tuple[str, str]]  
    mutex_actions: list[tuple[str, str]]     
    bounded_durations: dict[str, tuple[float, float]]  
    cascade_dependencies: dict[str, list[str]]  
    dead_end_conditions: list[str]           
    recovery_options: list[str]              
    metadata: dict[str, Any] = field(default_factory=dict)