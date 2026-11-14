# STAB-015.01: handoff наступної ітерації

**Iteration 3 implementation completed locally, 2026-11-15; no rollout.**
Integration started from verified `4fe11be` (merged PR #24 / Accepted ADR).
The following table supersedes the original OPEN status; the historical handoff
below preserves the original scope and evidence, not current unresolved defects.

| Task | Implemented result / current evidence |
| --- | --- |
| STAB-003 | [Vite 6.4.6 / Vitest 4.1.12 / Node 22](../frontend-toolchain.md); application versions unchanged; remaining non-Vite advisories explicit. |
| STAB-015.03a | [Exact-key conflict normalization](../generation-job-deduplication.md), caller ownership and bounded winner-finalization handling; no package admission. |
| STAB-015.05a | [Per-job read-only CLI](../generation-recovery-inspection.md), bounded evidence and unknown transport outcomes; no recovery actions. |
| STAB-015.07a | [DB/schema readiness](../database-readiness.md), additive minimal `/health/ready`; connection/statement bounds, not a strict total DNS/HTTP deadline. |
| STAB-015.07b | [Operations coverage/queue CLI](../generation-operations.md), today/tomorrow and 06:00 Kyiv; no historical on-time or worker-health inference. |

Both reports use an orchestrator-owned independent read-only snapshot and coverage
helper. Shared app wiring, config opt-out, Compose Node version and documentation
were integrated centrally. Final verification is in [CURRENT_STATE](../CURRENT_STATE.md).
Current live bind mounts, containers, credentials, data and scheduler were not changed.

## Historical preparation and scope

**Prepared 2026-11-15; implementation had NOT started at this checkpoint.** Source baseline:
`2b716598ec078cafe2146c2e4d66f1ec139dfab0`, PR #23. Local і remote
`feature/main-page-start` збігалися під час preflight. D1–D8 у
[ADR](STAB-015-generation-execution.md) **Accepted 2026-11-14**; цей handoff
не змінює їх і не дозволяє paid activation. Чинні контракти й обмеження —
[architecture](../architecture.md), [paid gate](../paid-execution.md),
[test safety](../testing-safety.md), [task backlog](STAB-015-backlog.md).

## Перевірений статус і незалежність

На цьому історичному checkpoint усі п'ять кандидатів були **OPEN**. Наявність базових API/tests не означала, що
описані нижче гарантії вже реалізовані. Backend cards зберігають свої IDs і
acceptance у backlog; тут уточнено delegation boundaries, не створено дублікати.

| Task | Доказ до iteration 3 | Запланований результат | Залежності / пріоритет |
| --- | --- | --- | --- |
| STAB-003 | Lockfile: root Vite 6.3.5; Vitest 1.6.1 та вкладені Vite 5.4.19. Compatible secure toolchain ще не інтегровано. | Узгоджений patched Vite/Vitest/Vue-plugin/Node tuple і lockfile, чинні frontend checks. | Незалежна від generation ADR; першочерговий security fix. |
| STAB-015.03a | [create_generation_job:348](../../backend/app/services/generation_job_service.py#L348) робить SELECT, потім unhandled commit/flush; [0005 index](../../backend/migrations/versions/0005_generation_jobs.py) вже забезпечує exact active-key uniqueness. | Контрольований duplicate result після саме цього unique conflict, збережена транзакція caller. | Не чекає ledger/D3 rollout; вузький existing-contract fix. |
| STAB-015.05a | [job detail:667](../../backend/app/services/generation_admin_service.py#L667) додає linked run, але не формує evidence-based per-job recovery report. | Read-only діагностика конкретного job ID; known / missing / unknown evidence. | Не залежить від .03a/.02/.04; не дозволяє recovery mutations. |
| STAB-015.07a | [Compose healthcheck](../../docker-compose.yml#L73) читає static `/api/signs`; [registered routes](../../backend/app/__init__.py) не мають окремої DB readiness. | Bounded read-only DB/schema readiness, окрема від liveness. | Не залежить від queue/accounting tasks; endpoint registration інтегрує orchestrator. |
| STAB-015.07b | [coverage:708](../../backend/app/services/generation_admin_service.py#L708) має date coverage, але немає aggregate queue/deadline report; [sign helper](../../backend/app/services/sign_service.py) має empty-set static fallback. | Aggregate enabled-sign coverage, queue depth/age та поточний verdict щодо 06:00 Europe/Kyiv. | D8 accepted; не потребує нової ledger/pause schema; невідомі причини позначати unknown. |

### STAB-003: security і compatibility scope

Офіційний [GHSA-p4f5-76q4-ffq7](https://github.com/vitejs/vite/security/advisories/GHSA-p4f5-76q4-ffq7)
(2026-11-10, Critical) описує RCE для network-exposed Vite dev server;
affected range включає 4.0.0–6.4.5, patched 6.x — 6.4.6. Обидві locked
Vite versions потрапляють у цей range. Це dependency finding, **не доказ
експлуатації або встановленої live-container версії**. Exploit/PoC не запускався.

6.4.6 — patch floor для цього advisory, не автоматичний вибір всього toolchain
або гарантія відсутності інших advisory. Перед реалізацією перевірити актуальні
primary release/security/peer requirements; обрати найменший сумісний supported
tuple. Root-only bump залишить вкладені Vite у Vitest/vite-node. Не застосовувати
blind `npm audit fix --force` або override несумісної major version.

Baseline: `@vitejs/plugin-vue` 5.2.3 має peers Vite 5/6;
[development Compose](../../docker-compose.yml#L145) — Node 20,
[frontend CI](../../.github/workflows/frontend-tests.yml#L31) — Node 22.
Node parity/support перевірити разом із chosen tuple; потрібні зміни image/CI
узгоджує orchestrator як частину цього scope, без live recreate.
STAB-002 loopback defaults зберегти; internal Vite `0.0.0.0` потрібний Docker.
Configuration defaults не доводять, що live ports уже перестворені.

## File ownership для незалежних worktrees

Шляхи з позначкою **new** — запропоновані місця майбутніх модулів, ще не файли
baseline. Якщо реалізація потребує іншої межі, спершу узгодити ownership з
orchestrator; не редагувати чужий worktree. Одна задача — один changeset або
попередньо погоджені вузькі commits; без unrelated cleanup.

| Owner / task | Власний write scope | Read-only/shared boundary |
| --- | --- | --- |
| STAB-003 | `frontend/package.json`, `frontend/package-lock.json`; `vite.config.js`, `vitest.config.js` і focused frontend test compatibility лише за потреби | Compose, CI і спільні docs — orchestrator. Не frontend redesign/SSR/POC feature work. |
| .03a | `backend/app/services/generation_job_service.py`, тільки create/dedupe transaction boundary; **new** `backend/tests/test_generation_job_dedupe_conflicts.py` | Models/index/schema unchanged; existing broad job tests змінює orchestrator лише за необхідності. |
| .05a | **new** `backend/app/services/generation_recovery_inspection_service.py`, `backend/utils/generation_job_inspect.py`, `backend/tests/test_generation_recovery_inspection.py` | Models, serializers, job/lifecycle services тільки читати; не редагувати .03a service. CLI first, без нового Admin endpoint у цій картці. |
| .07a | **new** `backend/app/services/readiness_service.py`, `backend/app/health_routes.py`, `backend/tests/test_readiness.py` | Orchestrator реєструє blueprint у `backend/app/__init__.py`; не змінювати live Compose healthcheck. |
| .07b | **new** `backend/app/services/generation_operations_service.py`, `backend/utils/generation_operations_report.py`, `backend/tests/test_generation_operations.py` | Existing date/sign/model/queue helpers читати; не змінювати legacy generation fallback або .05a module. CLI first, без dashboard/alert delivery. |

**Orchestrator-only:** README, CURRENT_STATE, architecture, ADR/backlog/handoff,
app factory/blueprint registration, existing admin/public route wiring, Compose/CI
за доведеної STAB-003 compatibility потреби. Shared harness/conftest, models,
migrations та public response contracts не входять до цієї п'ятірки; потреба їх
зміни — явний scope review, не паралельний opportunistic refactor.

## Уточнені контракти та acceptance

### STAB-015.03a

- Normalize тільки active exact-key index violation; unrelated IntegrityError
  не перетворювати на duplicate success. Зберегти `skip_duplicate=True` result
  `(existing_job, False)` і чинну validation error при `False`.
- Не змінювати dedupe hash, partial unique index або scope на package; це .03b.
  `commit=False` callers не втрачають сторонні pending writes через blanket rollback.
- Після raced INSERT reload має враховувати winner, що вже завершився: bounded
  retry/controlled conflict, не повернення non-active job як active duplicate.
- Two independent PostgreSQL sessions/barriers; same-key і unrelated-key;
  commit/flush, caller transaction preservation та unrelated DB failures.
  Read/create fake jobs у disposable DB; provider transport заборонений.

### STAB-015.05a — один job, без recovery actions

- Вхід: один job ID; bounded item/attempt summary, linked run, owner/timestamps,
  published/missing scope, missing links і unknown evidence. CLI exit/report
  contract документувати; not-found/invalid input не маскувати як healthy job.
- Прострочений lock не доводить worker death. Без нового ledger відсутність
  attempt/result не доводить, що transport не відбувся. Не радити safe automatic
  retry/refund на підставі legacy state.
- SELECT-only transaction, no flush/commit/claim/stale closer/generation;
  no raw prompts/provider responses/secrets. Fixtures: published-but-not-finalized,
  missing run, failed/partial/running job, stale timestamps, empty history.
- Немає aggregate fleet freshness/SLO або загальної queue depth: це .07b.

### STAB-015.07a — readiness

- Proposed additive route `GET /health/ready`: `200` тільки за bounded DB/schema
  readiness; `503` при недоступній DB/timeout/schema mismatch. Minimal sanitized
  payload, без credentials/DSN/SQL exception. Existing `/api/signs` не змінюється.
- Expected schema contract узгодити з поточним Alembic head **read-only**; не
  запускати migration або `create_all`. Connection/statement timeouts мають
  обмежувати весь probe, не лише успішний SELECT.
- No DB readiness → worker-health inference. App liveness, producer activity,
  quota і content freshness не входять у цей endpoint.
- Integration wiring один orchestrator-owned diff; handler tests можуть
  реєструвати blueprint у test app. DB-down/schema/timeout tests через fakes та
  isolated fixtures, без зупинки development PostgreSQL.

### STAB-015.07b — агрегована операційна картина

- Вхід: business-date/locale/type scope і injectable clock. Поточні enabled signs
  з DB, published/missing coverage; queued/running/failed counts та oldest age.
  Нуль enabled signs — explicit configuration/empty-set state, не fixed 13 і
  не fabricated healthy coverage. Не змінювати generation helper fallback тут.
- Deadline 06:00 Europe/Kyiv, DST-aware. До deadline incomplete — pending;
  incomplete після deadline — actionable failure. Full coverage опівдні не є
  доказом, що вчора/сьогодні о 06:00 усе було published: historical verdict unknown
  без достатніх даних. Withdraw/update й enabled-sign зміни не вигадують history.
- API liveness, DB readiness, worker progress, content freshness — окремі поля.
  Quota/worker failure reasons тільки за evidence; відсутній durable pause/heartbeat
  позначити unavailable/unknown, не додавати їх реалізацію. Alert delivery pending.
- SELECT-only; без scan повних prompts/attempt payloads. Tests: before/at/after
  deadline, Kyiv DST, enabled/disabled/zero signs, partial publication, queue ages,
  empty queue, missing worker evidence; no paid calls/commits.
- Не дублювати per-job .05a recovery explanation або надавати recovery authority.

### STAB-003

- Lockfile clean install відтворює chosen tuple; root і nested dependency trees
  перевірені. Security/peer/Node rationale описано, решта dependency changes пояснені.
- Чинні route/archive tests, vue-tsc, build і fixture POC checks проходять.
  Не послаблювати тести/typecheck для upgrade; виправлення вузько сумісні.
- Preserve /api proxy, container listener і loopback host defaults. Нові dependency
  versions не вважати застосованими до live containers; runtime rollout окремо.

## Verification план для майбутньої реалізації

Наведені команди **не виконувалися** під час STAB-015.01. Перед implementation
повторити branch/HEAD/dirty/runtime preflight, залишити scheduler stopped і
використовувати isolated worktrees. Не змінювати development bind-mounted source.

Backend tests — один orchestrator/test-DB owner, послідовно через STAB-007 harness;
не raw pytest. Він прибирає credentials і забороняє unexpected transport/processes.
Спочатку safety mock guards за testing-safety.md, потім focused selectors після
створення зазначених tests, наприклад:

```bash
bash scripts/backend-test.sh tests/test_generation_job_dedupe_conflicts.py
bash scripts/backend-test.sh tests/test_generation_recovery_inspection.py
bash scripts/backend-test.sh tests/test_readiness.py
bash scripts/backend-test.sh tests/test_generation_operations.py
bash scripts/backend-test.sh
```

Full suite — на інтегрованому результаті після shared wiring, а не висновок із
agent-local runs. Reuse focused successful checks, якщо відповідний код не змінений.
Середовище має залишатися ізольованим; failure of safety preflight — blocker,
не привід обходити guard. No generation CLI smoke tests на development DB.

Frontend — із `frontend/` isolated worktree, без real credentials/dev dotenv:

```bash
npm ci
npm run typecheck
npm test -- --run
npm run build
npm run poc:check
```

`poc:check` використовує injected fixtures та локальний loopback HTTP harness;
це не static check і не доказ browser capture/production rendering. Не запускати
`poc:verify`, live backend probes або advisory exploit автоматично. Package install
і loopback test listener належать окремій implementation session, не цьому audit.

Фінально: `git diff --check`, narrow scope review, docs link/claim checks, SAFE-001
regressions у full backend suite; Compose config validation тільки якщо змінено
Node image/config. Жодних paid calls, development DB writes, scheduler restarts,
Docker recreates, pushes або PR creation як частини verification.

## Рекомендована координація і наступний checkpoint

1. STAB-003 — перший security changeset; .03a — наступний вузький backend fix.
2. .05a, .07a, .07b незалежні за data contract і можуть готуватися в окремих
   worktrees; інтеграція shared wiring/docs та всі DB suites послідовні.
3. За native delegation — до трьох implementation agents одночасно, лише коли
   окрема implementation task це дозволяє; інакше послідовно. У STAB-015.01
   implementation agents не запускалися.
4. Стабільний checkpoint: compatible frontend, normalized exact duplicates,
   read-only per-job diagnostics, DB readiness та aggregate coverage visibility.
   Це **не** queue-first paid-production readiness: ledger/admission/fencing/
   recovery/pause/async/keyless prerequisites у backlog усе ще обов'язкові.

Власнику не потрібно знову обирати D1–D8. Наступні owner/operator inputs — numeric
cap, measured timeout/lease values, operator/alert/retention settings, compatibility
window, fairness/configuration параметри та окреме rollout approval за P1–P8 ADR.
