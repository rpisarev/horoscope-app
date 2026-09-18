# Instructions for coding agents

## Repository workflow

The main project working branch is `feature/main-page-start`. It is the current integration baseline, not limited to main-page work. Always inspect the actual checked-out branch, HEAD, and working-tree status before editing.

Read [README.md](README.md), [docs/CURRENT_STATE.md](docs/CURRENT_STATE.md), and relevant source. See [docs/architecture.md](docs/architecture.md) for current flows.

Use this source-of-truth order: current repository code, tests, configuration, Git history, documentation, then old chat/handoff context. Investigate disagreements. Keep verified behavior, known issues, risks, open questions, history, and proposals distinct.

## Git safety

- Never discard or overwrite uncommitted user work.
- Do not reset, rebase, force-push, or rewrite history unless explicitly requested.
- Do not merge branches based on names; inspect their commits and differences.
- Prefer small reviewable changes; avoid unrelated refactors, dependency changes, and cleanup.
- Stage, commit, or push only within the task's authorization.

## Backend testing and database safety

From the repository root, use:

```bash
bash scripts/backend-test.sh
```

The script recreates, migrates, tests against, and normally drops `horoscope_test`. Any `TEST_DB_NAME` override must name a disposable test database.

Never point raw pytest at development data or bypass its guard with `ALLOW_PYTEST_ON_DEV_DB=1`: fixtures truncate mutable tables. Do not delete Docker volumes or run data-changing smoke examples as routine verification. Schema changes use Alembic migrations, not `db.create_all()`.

## Frontend verification

Inspect `frontend/package.json` first. Existing commands, from `frontend/`, include:

```bash
npm test -- --run
npm run build
```

Use non-watch tests. A Vite build does not type-check the application. Report checks actually run and unavailable checks; do not invent scripts or add tooling for an unrelated task.

## Generation and API guardrails

- Keep ordinary verification on stub/fake providers. Do not enable or execute paid OpenAI generation unless explicitly requested. Starting the scheduler or generation utilities can write data; gates differ between execution paths.
- Preserve separation between queue orchestration, lifecycle/audit records, prompt construction/validation, providers, and persistence unless redesign is explicitly in scope.
- The prompt pipeline uses sign/date for routing, storage, variation, and audit metadata, not direct creative instructions. Preserve that constraint unless the task changes it.
- Preserve public contracts unless explicitly changing them, including the `/api/signs` array and forecast aliases (`sign`/`sign_key`, `day`/`date`, `text`/`forecast`, `model_version`/`model_name`).
- Public `GET /api/forecast` is read-only and published-only: missing/unpublished data returns `404 forecast_not_published`, including when a provider is configured. Existing published stubs remain readable.
- Product today comes from `APP_TIMEZONE` (default `Europe/Kyiv`) through the shared backend helper and `/api/meta`. Keep domain dates as `YYYY-MM-DD`, operational timestamps in UTC, and never substitute browser/server-local today.
- Tests encode current behavior, including known issues; they do not make legacy behavior approved permanent design. Scope and test requested contract changes.
- Derive active-sign coverage from database metadata, not a hardcoded seed count. Check schema, serializers, public API fields, and frontend presentation data separately; similarly named concepts are not necessarily equivalent.

## Frontend guardrails

- Inspect both route definitions and affected view validators before changing navigation.
- Forecast-day identity is `/horoscope/:sign/:YYYY-MM-DD`; legacy archive-day URLs only validate and replace to that route. Invalid explicit signs/dates render contextual NotFound without fallback or clamping.
- ArchiveMonth clickability comes from sign-scoped `/api/archive/month` `has_forecast`, not calendar position or aggregate counts. Metadata failure must not block explicit-month availability.
- Preserve intended interactions, including Wheel selection on click/Enter/Space, unless the task changes them. Preserve animation cleanup.
- Distinguish source evidence and reproduced bugs from speculative synchronization risks.

## Documentation and completion

Update `docs/CURRENT_STATE.md` after meaningful milestones that change its recorded state. Update architecture documentation when flows, ownership, or configuration boundaries change. Keep README as the setup entry point; do not record transient SHAs or test counts in these agent rules.

Review the diff and run checks appropriate to the change. Report results and limitations; reuse successful checks when relevant code is unchanged. For documentation-only work, verify claims, links, whitespace, and file scope. Keep proposed changes separate from approved or implemented behavior.
