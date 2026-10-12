    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
3 passed, 1 warning in 0.44s

 ✓ components/ProbabilityBar.test.tsx  (3 tests) 86ms

 Test Files  1 passed (1)
      Tests  3 passed (3)
   Start at  09:59:15
   Duration  1.17s (transform 142ms, setup 0ms, collect 307ms, tests 86ms, environment 488ms, prepare 74ms)

................                                                         [100%]
16 passed in 7.90s

Phase 2 (partial): owner auth (argon2id), sessions, CSRF, lockout, CLI, API routes: 23 backend tests pass; live uvicorn smoke test: health ready=ok, anonymous POST -> 401.
.............................                                            [100%]
29 passed in 10.83s

Phase 3: fixed bug found by test (CSV row with invalid odds kept its fixture; rows are now accepted atomically).

Phase 4: 32 backend tests pass. Backtest run on SYNTHETIC data (python scripts/run_backtest.py synthetic) -> docs/MODEL_REPORT.md. Bug found by test: crash on degenerate grid in walk_forward; now skipped and counted.
tests/test_phase5.py:130: AssertionError
=========================== short test summary info ============================
FAILED tests/test_phase5.py::test_chat_endpoint_auth_unconfigured_and_stream
1 failed, 72 passed in 12.67s
.                                                                        [100%]
73 passed in 12.27s

Phase 5: 73 backend tests pass incl. 30-utterance eval on MockLLM (tests orchestration only). Bugs found by tests: odds lookup matched past fixtures (now scheduled only). Live LLM adapters UNVERIFIED.

Phase 6: 84 backend tests pass. Added predictions table (DB CHECK: live predictions need cutoff and created_at before kickoff; ORM-level immutability + supersede chain), stale-odds thresholds tightening toward kickoff, model-vs-market comparison with theoretical EV gated on fresh price + valid prediction, explorer API, analysis endpoint, favourites. Bugs found by tests: none in product code (two test mistakes fixed). NOT verified: immutability at raw-SQL level (needs a Postgres trigger in a migration), Postgres, closing-line comparison.

Phases 7-13: 102 backend tests pass. See docs/TEST_REPORT.md and docs/AUDIT.md.
