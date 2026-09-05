"""Regression tests for Temporal activity timeouts in workflows.py.

Static AST analysis (no runtime import — the workflow module is guarded by
Temporal's sandbox import semantics, and importing it at test time would
require a running Temporal environment).

Guards: the LLM-calling activity (extract_events_v7_activity) must have a
start_to_close_timeout of at least 60 minutes — LLM extraction via OpenRouter
can legitimately take longer than the previously configured 30 minutes.
"""

import ast
import pathlib
from datetime import timedelta

import pytest

WORKFLOWS_PATH = pathlib.Path(__file__).resolve().parent.parent / "src" / "eth_pipeline" / "workflows.py"

LLM_ACTIVITY_NAME = "extract_events_v7_activity"
MIN_TIMEOUT_SECONDS = 3600  # 60 minutes


def _resolve_name(node: ast.expr) -> str | None:
    """Resolve a simple Name/Attribute chain to its dotted string form."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _resolve_name(node.value)
        if parent is not None:
            return f"{parent}.{node.attr}"
    return None


def _eval_timedelta_seconds(node: ast.expr) -> float | None:
    """Evaluate a timedelta(...) call literal, supporting seconds= and/or minutes=."""
    if not isinstance(node, ast.Call):
        return None
    if _resolve_name(node.func) not in ("timedelta", "datetime.timedelta"):
        return None
    kwargs = {kw.arg: kw.value for kw in node.keywords}
    try:
        seconds = 0.0
        if "seconds" in kwargs:
            seconds += float(ast.literal_eval(kwargs["seconds"]))
        if "minutes" in kwargs:
            seconds += float(ast.literal_eval(kwargs["minutes"])) * 60
    except (ValueError, TypeError):
        return None
    return seconds


def _find_llm_activity_calls() -> list[tuple[int, float]]:
    """Find execute_activity calls for the LLM activity.

    Returns list of (line_number, timeout_seconds). Only calls with an
    evaluable timedelta start_to_close_timeout are returned.
    """
    source = WORKFLOWS_PATH.read_text()
    tree = ast.parse(source)
    found: list[tuple[int, float]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _resolve_name(node.func) != "workflow.execute_activity":
            continue
        if not node.args or _resolve_name(node.args[0]) != LLM_ACTIVITY_NAME:
            continue
        timeout = None
        for kw in node.keywords:
            if kw.arg == "start_to_close_timeout":
                timeout = _eval_timedelta_seconds(kw.value)
                break
        if timeout is not None:
            found.append((node.lineno, timeout))
    return found


def test_llm_activity_call_sites_exist():
    """At least one execute_activity call site for the LLM activity must exist.

    Guards against the timeout test silently passing when the activity is
    renamed or removed — if this fails because of a rename, update
    LLM_ACTIVITY_NAME in this file in the same commit.
    """
    found = _find_llm_activity_calls()
    assert found, (
        f"No workflow.execute_activity call for {LLM_ACTIVITY_NAME} with a "
        f"timedelta start_to_close_timeout found in {WORKFLOWS_PATH}. "
        "If the activity was renamed, update LLM_ACTIVITY_NAME here."
    )


def test_llm_activity_timeout_at_least_60_minutes():
    """Every LLM activity call site must have start_to_close_timeout >= 60 minutes."""
    found = _find_llm_activity_calls()
    offending = [(line, secs) for line, secs in found if secs < MIN_TIMEOUT_SECONDS]
    minimum = min((secs for _, secs in found), default=None)
    assert not offending, (
        f"{LLM_ACTIVITY_NAME} is invoked with start_to_close_timeout below "
        f"{MIN_TIMEOUT_SECONDS}s (60 minutes). Offending call site(s) "
        f"{WORKFLOWS_PATH.relative_to(WORKFLOWS_PATH.parent.parent)}: "
        + ", ".join(f"line {line} = {timedelta(seconds=secs)} ({secs}s)" for line, secs in offending)
        + f". Minimum found: {minimum}s. LLM extraction calls can legitimately "
        "take longer than 30 minutes; a too-short timeout causes spurious "
        "activity failures and wasteful retries."
    )
