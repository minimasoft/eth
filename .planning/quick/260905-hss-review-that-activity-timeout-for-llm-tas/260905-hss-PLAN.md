---
phase: quick-260905-hss
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/eth_pipeline/workflows.py
  - tests/test_workflow_timeouts.py
autonomous: true
requirements: []
estimate:
  tokens: 25000
  raw_tokens: 12500
  tasks: 2
  confidence: med
must_haves:
  truths:
    - The LLM extraction activity (`extract_events_v7_activity`) is invoked with a `start_to_close_timeout` of at least 30 minutes.
    - A regression test fails if any future change lowers the LLM activity timeout below 30 minutes.
  artifacts:
    - src/eth_pipeline/workflows.py (timeout raised)
    - tests/test_workflow_timeouts.py (regression test)
  key_links:
    - workflows.py execute_activity(extract_events_v7_activity, start_to_close_timeout=...) must be >= 1800s
---

<objective>
Review and fix the Temporal activity timeout for LLM tasks: ensure the activity timeout for LLM-calling activities is at least 30 minutes.

Purpose: LLM extraction calls (`extract_events_v7_activity`, which calls OpenRouter via `provider.extract_events_v7`) can legitimately take longer than the currently configured 15 minutes; a too-short `start_to_close_timeout` causes spurious activity timeouts and wasteful retries (up to 3 attempts) on long LLM responses.

Output: `extract_events_v7_activity` invoked with `start_to_close_timeout >= timedelta(minutes=30)` in `src/eth_pipeline/workflows.py`, plus a unit regression test guarding the floor.
</objective>

<execution_context>
@/home/u/src/eth/.opencode/gsd-core/workflows/execute-plan.md
@/home/u/src/eth/.opencode/gsd-core/templates/summary.md
</execution_context>

<context>
Review findings (already investigated):

- `src/eth_pipeline/workflows.py:121-130` — the ONLY LLM-calling activity is `extract_events_v7_activity`. It is currently invoked with `start_to_close_timeout=timedelta(seconds=900)` (15 minutes) and `RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=5), backoff_coefficient=2.0)`. This is BELOW the 30-minute threshold → fix required.
- All other `execute_activity` call sites in `DocumentProcessingV7Workflow.run` are non-LLM (status updates, DB reads/writes, text extraction, chunking) — their timeouts (10s–10min) are out of scope for this review.
- `resolve_references_v7_activity` (workflows.py:155-159, 120s) is DB-only — grep of `src/eth_pipeline/activities/resolve_references_v7.py` confirms no LLM/provider calls. No change needed.
- No existing test asserts on the 900s value (`tests/test_v7_workflow.py` has no timeout assertions) — safe to change.
- The retry policy on the extraction call (max 3 attempts) is intentional and must be preserved.
- Per AGENTS.md: run tests ONLY via `./test.sh --unit` (this test uses no stateful fixtures, so it auto-qualifies as unit). Never run pytest/uv ad-hoc on the host otherwise.

@src/eth_pipeline/workflows.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add regression test asserting LLM activity timeout >= 30 minutes</name>
  <files>tests/test_workflow_timeouts.py</files>
  <behavior>
    - Test 1: parsing `src/eth_pipeline/workflows.py` with `ast`, for every `workflow.execute_activity(...)` call whose first positional argument is the name `extract_events_v7_activity`, the `start_to_close_timeout` keyword is a `timedelta(...)` call whose computed `total_seconds()` is >= 1800.
    - Test 2: the same scan finds at least one such call site (guards against the test silently passing when the activity is renamed/removed — if renamed, update the test's expected name in the same commit).
  </behavior>
  <action>
    Create `tests/test_workflow_timeouts.py` as a pure unit test (no DB, no stateful fixtures — it must auto-qualify for `./test.sh --unit`). Implement by reading the source file `src/eth_pipeline/workflows.py` from disk relative to the repo root, parsing it with `ast`, and walking `ast.Call` nodes. Match calls where the func attribute chain is `workflow.execute_activity` and the first arg resolves to `extract_events_v7_activity`. For the `start_to_close_timeout` keyword, evaluate the `timedelta(...)` call literal (support `seconds=`, `minutes=`, or both) to compute total seconds. Assert `total_seconds >= 1800`. Do NOT import `eth_pipeline.workflows` at test time to check runtime values — the workflow class is guarded by Temporal's sandbox import semantics; static AST analysis of the source is the reliable gate here. Expect the test to FAIL (red) against the current 900s configuration — that is the correct TDD starting point.
  </action>
  <verify>
    <automated>./test.sh --unit tests/test_workflow_timeouts.py</automated>
  </verify>
  <done>Test runs under `./test.sh --unit` and FAILS with the current 900-second timeout, reporting the offending value and line.</done>
</task>

<task type="auto">
  <name>Task 2: Raise extract_events_v7_activity start_to_close_timeout to 30 minutes</name>
  <files>src/eth_pipeline/workflows.py</files>
  <action>
    In `src/eth_pipeline/workflows.py`, at the `extract_events_v7_activity` call site (line ~124), change `start_to_close_timeout=timedelta(seconds=900)` to `start_to_close_timeout=timedelta(minutes=30)`. Keep the existing `retry_policy` (maximum_attempts=3, initial_interval=5s, backoff_coefficient=2.0) exactly as-is. Do NOT touch any other `execute_activity` call site — the non-LLM timeouts (10s–10min) are deliberately small and correct for their activities, and `resolve_references_v7_activity` makes no LLM calls. This satisfies the review requirement that LLM-task activity timeouts are at least 30 minutes.
  </action>
  <verify>
    <automated>./test.sh --unit tests/test_workflow_timeouts.py && rg -n "start_to_close_timeout=timedelta\(minutes=30\)" src/eth_pipeline/workflows.py</automated>
  </verify>
  <done>The extraction activity is invoked with a 30-minute start_to_close_timeout, the regression test passes, and no other call site in workflows.py was modified (git diff shows exactly one changed line).</done>
</task>

</tasks>

<verification>
- `./test.sh --unit` passes (the new regression test plus the rest of the unit suite).
- `git diff src/eth_pipeline/workflows.py` shows exactly one line changed: 900s → 30min on the `extract_events_v7_activity` call.
- Review requirement satisfied: LLM activity timeout >= 30 minutes, guarded by a test.
</verification>

<success_criteria>
- The only LLM-calling activity (`extract_events_v7_activity`) has `start_to_close_timeout=timedelta(minutes=30)` (>= 1800s) in `src/eth_pipeline/workflows.py`.
- `tests/test_workflow_timeouts.py` enforces the 30-minute floor via static AST analysis and passes under `./test.sh --unit`.
- Retry policy on the extraction call is unchanged.
</success_criteria>

<output>
Create `.planning/quick/260905-hss-review-that-activity-timeout-for-llm-tas/260905-hss-SUMMARY.md` when done
</output>
