"""
LLM-guided temporal plan repair.

Uses an LLM (Claude via Anthropic API) as the plan repair generator
in an LLM-Modulo-style loop:

    disrupted plan + failure report → LLM proposes repair → validator checks → score

Same interface as local_shift_repair and replan_naive:
    (disrupted, config, report) → RepairResult

Requires ANTHROPIC_API_KEY environment variable.
"""

from __future__ import annotations

import copy
import json
import os
from typing import Any

from trlc_bench.models import (
    DomainConfig,
    FailureReport,
    PlanAction,
    RepairResult,
    TemporalPlan,
)
from trlc_bench.validator import validate_plan


def llm_repair(
    disrupted: TemporalPlan,
    config: DomainConfig,
    report: FailureReport,
    max_attempts: int = 3,
    model: str = "claude-sonnet-4-20250514",
) -> RepairResult:
    """
    LLM-guided repair: ask an LLM to fix the disrupted plan.

    Loop:
      1. Build prompt with disrupted plan + failure report + constraints
      2. LLM proposes a repaired plan
      3. Validate the proposal
      4. If invalid, feed violations back to LLM and retry
      5. Return best attempt

    Args:
        disrupted: The broken temporal plan.
        config: Domain configuration with constraints.
        report: Failure report describing what broke.
        max_attempts: Maximum LLM calls before giving up.
        model: Anthropic model to use.

    Returns:
        RepairResult with the LLM's best repair attempt.
    """
    log: list[str] = []

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return RepairResult(
            repaired_plan=copy.deepcopy(disrupted),
            strategy_name="llm_repair",
            repair_actions_taken=["ERROR: ANTHROPIC_API_KEY not set"],
            success=False,
        )

    # Build the system prompt
    system_prompt = _build_system_prompt(config)

    # Build initial user prompt
    user_prompt = _build_repair_prompt(disrupted, config, report)

    best_plan = copy.deepcopy(disrupted)
    best_valid = False
    messages = []

    for attempt in range(1, max_attempts + 1):
        log.append(f"Attempt {attempt}/{max_attempts}")

        if attempt == 1:
            messages = [{"role": "user", "content": user_prompt}]
        # else: messages already has the conversation history with feedback

        # Call the LLM
        try:
            response_text = _call_anthropic(
                api_key=api_key,
                model=model,
                system=system_prompt,
                messages=messages,
            )
            log.append(f"LLM response received ({len(response_text)} chars)")
        except Exception as e:
            log.append(f"LLM call failed: {e}")
            break

        # Parse the plan from the response
        parsed_plan = _parse_plan_from_response(response_text, disrupted)

        if parsed_plan is None:
            log.append("Failed to parse plan from LLM response")
            # Ask LLM to try again with correct format
            messages.append({"role": "assistant", "content": response_text})
            messages.append({
                "role": "user",
                "content": (
                    "I couldn't parse a valid plan from your response. "
                    "Please output ONLY the plan in this exact format, "
                    "one action per line:\n"
                    "<start_time>: (<action_name> <arg1> <arg2> ...) [<duration>]\n\n"
                    "Example:\n"
                    "0.000: (navigate r1 wp0 wp1) [3.000]\n"
                    "3.000: (collect-sample r1 s1 wp2) [3.000]"
                ),
            })
            continue

        # Validate
        validation = validate_plan(parsed_plan, config)

        if validation.is_valid:
            log.append(f"Attempt {attempt}: VALID plan produced")
            best_plan = parsed_plan
            best_valid = True
            break
        else:
            log.append(
                f"Attempt {attempt}: invalid ({len(validation.violations)} violations)"
            )
            best_plan = parsed_plan

            # Build feedback for next attempt
            violation_text = "\n".join(f"- {v}" for v in validation.violations)
            messages.append({"role": "assistant", "content": response_text})
            messages.append({
                "role": "user",
                "content": (
                    f"Your proposed plan has {len(validation.violations)} violations:\n"
                    f"{violation_text}\n\n"
                    "Please fix these violations and output the corrected plan. "
                    "Remember:\n"
                    "- All deadlines must be met\n"
                    "- Ordering constraints must be respected\n"
                    "- Bounded durations must be within [d_min, d_max]\n"
                    "- No mutex actions can overlap\n\n"
                    "Output ONLY the corrected plan lines."
                ),
            })

    return RepairResult(
        repaired_plan=best_plan,
        strategy_name="llm_repair",
        repair_actions_taken=log,
        success=best_valid,
        metadata={"attempts": min(attempt, max_attempts) if 'attempt' in dir() else 0},
    )


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _build_system_prompt(config: DomainConfig) -> str:
    """Build the system prompt with domain constraints."""
    parts = [
        "You are a temporal plan repair expert.",
        f"Domain: {config.domain_name} ({config.ergodicity})",
        "",
        "CONSTRAINTS YOU MUST RESPECT:",
    ]

    if config.deadlines:
        parts.append("Deadlines (action must END before this time):")
        for name, dl in config.deadlines.items():
            parts.append(f"  - {name}: t <= {dl}")

    if config.ordering_constraints:
        parts.append("Ordering (first must end before second starts):")
        for before, after in config.ordering_constraints:
            parts.append(f"  - {before} → {after}")

    if config.bounded_durations:
        parts.append("Bounded durations [min, max]:")
        for name, (dmin, dmax) in config.bounded_durations.items():
            parts.append(f"  - {name}: [{dmin}, {dmax}]")

    if config.mutex_actions:
        parts.append("Mutex (cannot overlap):")
        for a, b in config.mutex_actions:
            parts.append(f"  - {a} ↔ {b}")

    parts.extend([
        "",
        "OUTPUT FORMAT (exactly this, nothing else):",
        "<start_time>: (<action_name> <arg1> <arg2> ...) [<duration>]",
        "",
        "Example:",
        "0.000: (navigate r1 wp0 wp1) [3.000]",
        "3.001: (collect-sample r1 s1 wp2) [3.000]",
    ])

    return "\n".join(parts)


def _build_repair_prompt(
    plan: TemporalPlan,
    config: DomainConfig,
    report: FailureReport,
) -> str:
    """Build the user prompt describing the failure and requesting repair."""
    plan_text = "\n".join(str(a) for a in plan.sorted_actions())

    parts = [
        "The following temporal plan has been disrupted and needs repair.",
        "",
        f"FAILURE: {report.failure_type}",
        f"Description: {report.description}",
        f"Severity: {report.severity}",
        f"Affected actions: {', '.join(report.affected_actions)}",
        "",
        "BROKEN CONSTRAINTS:",
    ]
    for bc in report.broken_constraints:
        parts.append(f"  - {bc}")

    parts.extend([
        "",
        "CURRENT (DISRUPTED) PLAN:",
        plan_text,
        "",
        "Please output a REPAIRED plan that satisfies all constraints.",
        "Minimize changes to the original plan timing.",
        "Output ONLY the plan lines, no explanation.",
    ])

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# LLM API call
# ---------------------------------------------------------------------------

def _call_anthropic(
    api_key: str,
    model: str,
    system: str,
    messages: list[dict[str, str]],
) -> str:
    """Call the Anthropic API and return the response text."""
    import requests

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 2048,
            "system": system,
            "messages": messages,
        },
        timeout=30,
    )

    if resp.status_code != 200:
        raise RuntimeError(f"Anthropic API error {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    return data["content"][0]["text"]


# ---------------------------------------------------------------------------
# Plan parsing from LLM response
# ---------------------------------------------------------------------------

def _parse_plan_from_response(
    response: str,
    original: TemporalPlan,
) -> TemporalPlan | None:
    """Parse a temporal plan from the LLM's response text."""
    import re

    pattern = re.compile(
        r"(?P<start>[0-9]+(?:\.[0-9]+)?)"
        r"\s*:\s*"
        r"\((?P<body>[^)]+)\)"
        r"\s*\[(?P<dur>[0-9]+(?:\.[0-9]+)?)\]"
    )

    actions = []
    for line in response.splitlines():
        m = pattern.search(line)
        if m:
            start = float(m.group("start"))
            parts = m.group("body").split()
            name = parts[0]
            args = parts[1:]
            dur = float(m.group("dur"))
            actions.append(PlanAction(
                start_time=start,
                name=name,
                args=args,
                duration=dur,
            ))

    if not actions:
        return None

    actions.sort(key=lambda a: (a.start_time, a.name))

    return TemporalPlan(
        actions=actions,
        domain=original.domain,
        problem=original.problem,
    )