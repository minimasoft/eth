---
phase: quick
plan: 260905-jsy
type: execute
wave: 1
depends_on: []
files_modified:
  - src/eth_pipeline/chunker.py
  - src/eth_pipeline/llm.py
  - docker-compose.yml
  - .env.example
  - README.md
  - tests/test_smart_chunker.py
autonomous: true
requirements: [QUICK-CHUNK-HALVE, QUICK-CHUNK-CONFIG, QUICK-CHUNK-AUDIT]

estimate:
  tokens: 35000
  raw_tokens: 24000
  tasks: 3
  confidence: med

must_haves:
  truths:
    - Default chunk target is 262144 chars (~50% of 524288), producing ~50-65k input tokens per LLM call instead of ~100-130k
    - CHUNK_SIZE_TARGET env var remains the single source of truth; setting it in .env overrides the new default
    - No other module defines a chunk-size constant — dead duplicate EXTRACTION_CHUNK_SIZE is gone
  artifacts:
    - src/eth_pipeline/chunker.py (DEFAULT_TARGET = 262144)
    - docker-compose.yml (both services default 262144)
    - .env.example and README.md documenting 262144
    - tests/test_smart_chunker.py asserting the new default
  key_links:
    - docker-compose.yml worker service CHUNK_SIZE_TARGET → SmartChunker env read at init (chunking runs in worker)
    - chunk_document_activity → SmartChunker() → env default → document_chunk rows → extract_events_v7 per-chunk LLM calls
---

<objective>
Halve the default LLM extraction chunk size (~100k tokens → ~50k per call) by changing the default target from 524288 to 262144 chars across code, Docker env, and docs; remove the dead duplicate `EXTRACTION_CHUNK_SIZE` constant from llm.py; and verify via audit + unit tests that `CHUNK_SIZE_TARGET` is honored at every call site so large documents chunk down steadily instead of timing out providers.

Purpose: Providers degrade or time out on ~100k uncached prompt-processing + ~30k generation in a single call. Halving the chunk size keeps big documents processing with steady per-chunk progress.

Output: Updated chunker default, single-source-of-truth config, updated tests/docs, passing `./test.sh --unit`.

**Quick task mode — constraints:**
- Only `./test.sh` (integration) and `./test.sh --unit` (host unit) may be run. Do NOT run `./run.sh` — user is currently processing on the dev stack; do not touch it.
- Changing the default only affects the next stack restart / next document; no DB migration needed (chunking is runtime behavior, not schema).
</objective>

<execution_context>
@/home/u/src/eth/.opencode/gsd-core/workflows/execute-plan.md
@/home/u/src/eth/.opencode/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/STATE.md

Findings from pre-planning code audit (all verified by grep):

1. **Single chunking path exists:** `SmartChunker` (`src/eth_pipeline/chunker.py`) is the only chunker. `chunk_document_activity` (`src/eth_pipeline/activities/chunk_document.py:40`) constructs `SmartChunker()` with no explicit target — it reads `CHUNK_SIZE_TARGET` env at init (chunker.py:148-151). No langchain/RecursiveCharacterTextSplitter remnants exist. `extract_events_v7` fetches chunks from `document_chunk` table — no re-chunking there.
2. **Current default:** `DEFAULT_TARGET = 524288` chars (512KB) ≈ 100-130k Spanish tokens at ~4-5 chars/token → matches the user's observed ~100k input tokens.
3. **Dead duplicate:** `EXTRACTION_CHUNK_SIZE = 400_000` at `src/eth_pipeline/llm.py:185` — defined with a comment, never imported or referenced anywhere else in the repo. Exactly the hardcoded-duplicate hazard to eliminate.
4. **Config plumbing already exists** (Phase 34): `docker-compose.yml` lines 125 and 156 (`CHUNK_SIZE_TARGET: ${CHUNK_SIZE_TARGET:-524288}` in api + worker), `.env.example` line 52-54 (commented), `.env` line 58-60 (commented — local file, edit but do not commit since `.env` is gitignored), `README.md` line 155 env-var table.
5. **Tests asserting the old default:** `tests/test_smart_chunker.py` — `test_default_target_size` (line 163) and `test_empty_env_var_falls_back_to_default` (line 177) assert `524288`. Other tests use explicit `target_size=` args and are unaffected.
6. Precedent for regression tests: quick task 260905-hss added an AST regression test guarding the activity timeout floor (`tests/test_activity_timeouts.py`). Follow a similar lightweight pattern for the chunk-size default.
</context>

<tasks>

<task type="auto">
  <name>Task 1: Halve default chunk target in code and remove the dead duplicate constant</name>
  <files>src/eth_pipeline/chunker.py, src/eth_pipeline/llm.py, tests/test_smart_chunker.py</files>
  <action>
**chunker.py:**
- Change `DEFAULT_TARGET: ClassVar[int] = 524288  # 512KB in chars` to `DEFAULT_TARGET: ClassVar[int] = 262144  # 256KB in chars (~50-65k tokens Spanish)` per goal "~50% of current".
- Update the class docstring sentence "The chunker uses CHUNK_SIZE_TARGET env var (default 524288 = 512KB)" to reflect 262144 = 256KB.

**llm.py:**
- Delete the dead `EXTRACTION_CHUNK_SIZE = 400_000` constant AND its explanatory comment block (lines ~181-185). It is referenced nowhere; keeping it invites someone to edit it and wonder why nothing changes. The single source of truth is `CHUNK_SIZE_TARGET` in chunker.py. (Note: `llm.py` was already dead-code-cleaned in quick task 260611-jzq — this constant is a leftover from that era.)

**tests/test_smart_chunker.py:**
- Update `test_default_target_size` and `test_empty_env_var_falls_back_to_default` to assert `262144`.
- Add one regression test (unit, no DB) in `TestConfigurableSize` — `test_default_is_half_of_previous_default`: asserts `SmartChunker.DEFAULT_TARGET == 262144`, and asserts the dead duplicate is gone via `import eth_pipeline.llm as llm_module; assert not hasattr(llm_module, "EXTRACTION_CHUNK_SIZE")`. This guards both regressions: someone re-raising the default, and someone re-adding a second chunk-size constant.
  </action>
  <verify>
    <automated>./test.sh --unit tests/test_smart_chunker.py -x -q</automated>
  </verify>
  <done>DEFAULT_TARGET is 262144, EXTRACTION_CHUNK_SIZE no longer exists, updated + new tests pass on host unit run.</done>
</task>

<task type="auto">
  <name>Task 2: Update config plumbing and docs to the new default</name>
  <files>docker-compose.yml, .env.example, .env, README.md</files>
  <action>
**docker-compose.yml:** In both the api service (line ~125) and worker service (line ~156) environment blocks, change `CHUNK_SIZE_TARGET: ${CHUNK_SIZE_TARGET:-524288}` to `CHUNK_SIZE_TARGET: ${CHUNK_SIZE_TARGET:-262144}`. The worker is the container that actually chunks — both lines must change so the values can't drift.

**.env.example:** Update the comment block at lines ~52-54: description "Target chunk size in characters (default: 524288 = 512KB)" → 262144 = 256KB, and the commented `# CHUNK_SIZE_TARGET=524288` → `# CHUNK_SIZE_TARGET=262144`.

**.env (local, gitignored — edit but never commit):** Apply the same comment-block update (lines ~58-60) so the local deployment documents the new default. Note for executor: user is actively processing on the dev stack — only edit the commented line, do not uncomment or restart anything.

**README.md:** Line 155 env table row `CHUNK_SIZE_TARGET` — change default column from `524288` (512KB) to `262144` (256KB) and keep the description accurate ("Target chunk size in chars").
  </action>
  <verify>
    <automated>grep -rn "524288" src/ docker-compose.yml .env.example README.md; test $(grep -c "262144" docker-compose.yml) -eq 2</automated>
  </verify>
  <done>No occurrence of 524288 remains in src/, docker-compose.yml, .env.example, or README.md; both docker-compose services default to 262144; git status shows .env is NOT staged (gitignored).</done>
</task>

<task type="auto">
  <name>Task 3: Audit call sites for hardcoded chunk-size duplicates and run full unit suite</name>
  <files>.planning/quick/260905-jsy-reduce-chunk-sizing-to-50-of-current-100/AUDIT.md</files>
  <action>
Complete the "used correctly everywhere" review the task requires. Do each check and record findings in AUDIT.md:

1. **Single-chunker check:** `grep -rn "SmartChunker" src/` — expect exactly one construction site: `activities/chunk_document.py` calling `SmartChunker()` with no explicit `target_size` (so it honors the env var). Any other construction with a literal target_size is a hardcoded duplicate — fix it to construct `SmartChunker()` bare, or pass through `CHUNK_SIZE_TARGET`.
2. **No second constant:** `grep -rniE "chunk.?size|target.?size" src/ | grep -v "CHUNK_SIZE_TARGET"` — expect only `chunker.py` `target_size` parameter plumbing (function params, `self.target_size`, `distribute_balanced`) and llm.py comments about chunking (prose only). Any numeric literal like 400_000, 512_000, 128_000 used as a chunk size is a duplicate — remove or route through the env var.
3. **Env plumb-through check:** `docker compose config` is NOT allowed (touches dev stack context? no — it's dry-run config only, but keep it out per the testing constraint; instead) verify statically: `grep -n "CHUNK_SIZE_TARGET" docker-compose.yml` shows the worker service (the chunking container) declares it; if it were missing the worker would silently fall back to the container's baked-in default — confirm the worker line exists.
4. **Consumer check:** confirm `extract_events_v7.py` and `workflows.py` do not compute their own chunk sizes — they iterate `document_chunk` rows produced by the chunker (already verified in planning, re-assert in the audit).
5. Run the full host unit suite to catch anything the targeted run missed.

If any check reveals a duplicate or un-honored call site, fix it in the same task (code edit + corresponding test) before recording the finding as resolved.
  </action>
  <verify>
    <automated>./test.sh --unit -q && test -f .planning/quick/260905-jsy-reduce-chunk-sizing-to-50-of-current-100/AUDIT.md</automated>
  </verify>
  <done>AUDIT.md records each check with its result; unit suite passes; no hardcoded chunk-size duplicate exists in src/.</done>
</task>

</tasks>

<verification>
- `./test.sh --unit -q` passes (includes updated TestConfigurableSize + new regression test).
- `grep -rn "524288" src/ docker-compose.yml .env.example README.md` returns nothing.
- `grep -rn "EXTRACTION_CHUNK_SIZE" src/ tests/` returns nothing.
- `grep -c "CHUNK_SIZE_TARGET" docker-compose.yml` returns 2 (api + worker), both defaulting to 262144.
- AUDIT.md documents the single-source-of-truth review.
</verification>

<success_criteria>
- Default chunk target is 262144 chars everywhere (code default, docker-compose, env docs, README) — halving per-chunk LLM input tokens to ~50-65k.
- `CHUNK_SIZE_TARGET` is the only chunk-size control; setting it overrides the default; no dead or duplicate constants remain.
- Unit tests pass without touching the dev stack; user's in-flight processing is undisturbed.
</success_criteria>

<output>
Create `.planning/quick/260905-jsy-reduce-chunk-sizing-to-50-of-current-100/260905-jsy-SUMMARY.md` when done
</output>
