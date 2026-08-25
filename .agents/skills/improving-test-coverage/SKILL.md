---
name: improving-test-coverage
description: How to raise unit-test coverage in Bank of Anthos by fanning out one child session per module (ledgerwriter, balancereader, transactionhistory, userservice, frontend, ui-angular) plus a shared build/CI foundation session. Use for any "improve/raise test coverage" request on this repo.
---

# Improving test coverage (parallel, one session per module)

Raise coverage on compliance-critical paths by dispatching one child session per module. All module paths are relative to the root of this repo (`jeffxiang/bank-of-anthos`). If the attached repo is something else, stop and confirm with the user.

Testing conventions (frameworks, mocking rules, PII rules, coverage thresholds) live in the `bofa-testing-bestpractices` knowledge note — follow it rather than re-deriving patterns here.

## Parameters per slice
- `TARGET_MODULE` — module path (e.g. `src/ledger/ledgerwriter`).
- `STACK` — `java` | `python` | `angular`.
- `CRITICALITY_THEME` — compliance area the module owns (transaction processing / auth / PII / audit logging).
- `TEST_FILE` — the single test file the slice may create or extend.
- `DEPTH` — `fast` (default) or `thorough`.
- `COVERAGE_FLOOR` — `thorough` only: 90 for compliance-critical modules, 70 otherwise.

## Kickoff (lead session, one batch)
1. Confirm the working repo is this one; never infer module paths from another repo.
2. Dispatch the foundation session and one session per slice-table row **in the same batch**. The foundation is concurrent, not a gate.
3. Give each slice its parameters plus the "don't touch shared files" rule.
4. Track sessions; land the foundation PR whenever it is ready, independent of slice PRs.

## Foundation session (owns all shared build/CI files)
1. Wire coverage into the Python `test-unit` target (`--cov --cov-report=xml`); add `pytest-cov` to `src/frontend/pyproject.toml`.
2. Bind the JaCoCo `report` goal to the `test` phase for the three Java ledger modules so a scoped `mvn -pl <module> test` emits `jacoco.xml`.
3. Add a `test:coverage` npm script for `ui-angular` (`ng test --code-coverage --watch=false`).
4. Add a CI workflow running `make test-unit` plus the Angular script, report-only (non-blocking) at first.
5. Report baseline coverage per service.

## Slice table (fan out once per row, in parallel)

| Slice | `TARGET_MODULE` | `STACK` | `CRITICALITY_THEME` | `TEST_FILE` |
|---|---|---|---|---|
| 1 | `src/ledger/ledgerwriter` | java | transaction processing + write path | `LedgerWriterControllerTest.java` |
| 2 | `src/ledger/balancereader` | java | JWT authz + cache/error paths | `BalanceReaderControllerTest.java` |
| 3 | `src/ledger/transactionhistory` | java | JWT authz + cache/error paths | `TransactionHistoryControllerTest.java` |
| 4 | `src/accounts/userservice` | python | auth/JWT signing + PII validation | `tests/test_userservice.py` |
| 5 | `src/frontend` | python | auth cookies, `/payment`, error handling | `tests/test_frontend.py` (new) |
| 6 | `src/ui-angular` | angular | form validation + error states | one existing `*.component.spec.ts` |

Each row is a disjoint build module, so runs never collide. Add slices by adding rows. `accounts/contacts` (already tested) and `loadgenerator` (not compliance-critical) are lower priority.

## Per-slice procedure

### 1. Scope
Read only the compliance-critical file(s) matching `CRITICALITY_THEME` and the nearest sibling test of `TEST_FILE`. Mirror that sibling's idiom exactly; introduce no new frameworks (JUnit 5 + Mockito for Java, `unittest`/`pytest` + `unittest.mock` for Python, Jasmine + `TestBed` for Angular).

### 2. FAST mode (default — PR open within minutes)
- Skip coverage measurement entirely: no baselines, no coverage numbers in the PR.
- Touch exactly one test file (`TEST_FILE`) and no production source.
- Write 2–4 tests, taken from the top of the priority list below and no further.
- Run only the narrowest command exercising `TEST_FILE`, once:
  - java: `mvn -pl <module> test -Dtest=<TestClass> -DfailIfNoTests=false -o`
  - python: `cd <TARGET_MODULE> && uv run pytest <TEST_FILE> -q`
  - angular: `cd src/ui-angular && npx ng test --watch=false --browsers=ChromeHeadlessNoSandbox --include <TEST_FILE>`
- Do not run the full module suite, `make test-unit`, `make checkstyle`, or other stacks — CI covers those.
- Open the PR as soon as that one command is green; do not wait for CI or chase lint nits. If a test is stubborn after two attempts, delete it and ship the passing ones. Timebox ~10 minutes; note anything cut in the PR body.

### 3. Coverage baseline (`thorough` only)
Scope coverage to `TARGET_MODULE`, using invocations that work on plain `main` (no foundation plumbing assumed):
- java: `mvn -pl <module> test org.jacoco:jacoco-maven-plugin:report` → read `<module>/target/site/jacoco/jacoco.csv`
- python: `cd <TARGET_MODULE> && uv run --with pytest-cov pytest --cov=. --cov-report=term-missing`
- angular: `cd src/ui-angular && npx ng test --code-coverage --watch=false --browsers=ChromeHeadlessNoSandbox`

Record starting line/branch coverage as the ratchet floor; new code must not lower it.

### 4. Write tests (compliance-first ordering)
1. Negative/error branches on `CRITICALITY_THEME` paths — every `throw`/non-2xx/exception branch gets an explicit test.
2. Edge cases and equivalence classes — boundary amounts, malformed account/routing numbers including unicode and emoji, whitespace/length bounds on PII fields.
3. Authorization mismatches — valid token but wrong account → 401; assert exact status codes.
4. Audit/alert side-effects — failure emits the alert, alert failure does not change the primary response, no alert on success.
5. Happy path last, only to close remaining gaps (`thorough` only).

Use synthetic PII only, generate ephemeral RSA keypairs for crypto, never commit keys or realistic SSNs, and mock at the boundary (DB, HTTP, JWT verifier, file/env) — never the unit under test.

### 5. Verify (`thorough` only)
Re-run the baseline command; confirm the module meets `COVERAGE_FLOOR` (line + branch for compliance-critical) and that pre-existing tests still pass. If the floor is missed, list uncovered lines/branches and add targeted tests rather than padding with happy-path duplicates.

### 6. Deliver
- One PR per module, so parallel reviews stay independent.
- PR body: in fast mode, list the branches now covered and state that coverage was intentionally not measured; in thorough mode, give starting → ending coverage plus paths deliberately left untested and why.
- Never touch shared files (`Makefile`, CI workflows, root `pom.xml`, dependency/lock files) — the foundation session owns them.

## Pointers
- Java slices dominate wall-clock time (Maven startup + Spring context). Use `-Dtest=<TestClass>` with a warm `~/.m2`; never run the reactor-wide `mvn test` in fast mode.
- Angular needs Node 16.10 (`nvm use 16.10.0`); `npm ci` is the slowest step, so reuse `node_modules` when present.
- Fast mode trades coverage guarantees for turnaround. Follow up with `DEPTH=thorough` on modules that must hit a floor — balancereader and transactionhistory are the lowest.
- The 90/70 floors are assumed org policy from the testing knowledge note; swap in real internal control thresholds for a non-demo rollout.
