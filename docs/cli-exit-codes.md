# Generation CLI exit codes

[`generate_forecast_package.py`](../backend/utils/generate_forecast_package.py)
and [`process_generation_jobs.py`](../backend/utils/process_generation_jobs.py)
report execution outcomes through their process exit codes. Their stdout headings,
fields, ordering, and optional item/error/job reports remain unchanged. Both
entry points retain `raise SystemExit(main())`.

| Outcome | Exit code |
| --- | --- |
| Package run returns `success`, including all items skipped because forecasts are already published | `0` |
| Package run returns `failed`, `partial_failed`, or `interrupted` | `1` |
| Package returns an existing active `running` run | `1` (completion is not established) |
| Worker processes only jobs whose returned status is `success` | `0` |
| Worker processes zero jobs | `0` |
| Any processed job is failed, partially failed, incomplete, cancelled, or has an unrecognized status | `1` |
| Argparse rejects missing/unknown options or invalid option types | `2` (unchanged) |
| Existing explicit validation/safety rejection raises `SystemExit(message)` | `1` at process level (unchanged) |

The package CLI accepts only `success` as a successful returned status; unknown
statuses also return `1`. It uses the lifecycle status, not counters: a preflight
denial can be failed with zero items and zero failed-item count. An all-skipped
package is reported by the lifecycle as `success`, not as a separate skipped run
status. Optional reports are printed before the exit result is returned.

The worker evaluates the returned jobs for this invocation. Unclaimed queued jobs,
including jobs left queued by existing OpenAI count limits, do not turn an empty
or otherwise successful batch into failure. This code does not promise that the
whole queue is drained or every date is covered. `--close-stale` retains its existing
cleanup/count reporting; the exit status describes the subsequently processed
batch. A mixed batch returns `1` if any processed job is unsuccessful. Interrupted
lifecycle runs already map to failed jobs; active `running` runs also use the
worker's existing unsupported-status failure path.

Unexpected exceptions remain uncaught, so failures in service execution or report
printing cannot become success. Keyboard interrupts retain normal Python behavior;
there is no new catch-all handler or custom signal exit code. Calling `main()`
directly returns the outcome integer; existing validation paths still raise their
original exceptions.

## Retry-missing no-work and retry exhaustion

The lifecycle's `run_retry_for_missing_forecasts()` returns `None` both when there
is no missing work and when its retry-run cap is reached. Previously the worker
treated either result as a successful job, even when coverage remained incomplete.
That ambiguity required a bounded service mapping fix in
[`_run_retry_missing_job`](../backend/app/services/generation_job_service.py).

If the initial missing-forecast query is empty, the job still succeeds without a
run. If the retry helper returns a run, its existing status mapping is preserved.
If it returns `None` after work was found missing, the worker helper rechecks
coverage for the same date, locale and forecast type:

- Complete coverage returns `None` and preserves success without a linked run.
- Remaining missing forecasts raise the existing `GenerationJobProcessingError`.
  The existing worker exception handler records a failed job with an error,
  clears its lock, and leaves `run_id` unset for a fresh job. The CLI returns `1`.

The error describes missing forecasts and notes that the retry cap may have been
reached; `None` alone does not prove a unique cause. Coverage uses the existing
active-sign query rather than a fixed sign count. The recheck observes current
coverage; it is not a new transaction/locking guarantee against later changes.
No lifecycle return type, queue states, claim algorithm, retry policy, provider
selection, publication rules, or serialized response fields change. Queue callers
other than the CLI also receive this corrected failed-job outcome. Direct callers
of the lifecycle retry helper retain its existing `None` contract.

## Verification boundary

[`test_generation_cli_exit_codes.py`](../backend/tests/test_generation_cli_exit_codes.py)
uses deterministic service mocks and no real app creation or dotenv reads. It
covers successful/all-skipped runs, preflight failures, partial/interrupted/active
statuses, empty and mixed batches, reported retry outcomes, unchanged output,
invalid invocation, uncaught errors, and real `__main__` guards via in-process
`runpy` (no subprocess). Existing CLI publication/paid-denial tests assert exit `1`.

[`test_generation_job_service.py`](../backend/tests/test_generation_job_service.py)
adds mocked retry-helper coverage and a database-backed worker regression with an
exhausted retry cap, both with and without published coverage. Provider construction
is forbidden by the regression mock. The existing test harness network/credential
guards and fake SDK protections remain unchanged.

The parent integration task ran verification serially through the
[disposable test harness](testing-safety.md) on 2026-11-14: **160 focused tests**
passed, then **397 full backend tests** passed. Both disposable projects cleaned
up. Agent-local AST, documentation-link and diff checks were separate from these
integrated runs. No real provider request or live database change was required.
