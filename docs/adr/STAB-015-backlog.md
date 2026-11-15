# STAB-015: backlog реалізації прийнятої архітектури

**D1–D8 Accepted — 2026-11-14; STAB-015.01 COMPLETED (documentation only).**
**Статуси реалізації нижче оновлюються окремо від Accepted policy.**
На baseline PR #23, `2b71659`, усі implementation cards були OPEN.
STAB-015.03a/.05a/.07a/.07b завершено в iteration 3. Iteration 4 додає .02a
(storage only) і .08c-A (production probe ban). Iteration 5 реалізує .02b, .03b
та .04a foundation; .02c має перевірені primitives, але final atomic admission і
transport coordinator залишаються залежністю .03c. .08c-B та інші незавершені
картки OPEN. Production activation лишається заблокованою.
STAB-003 toolchain також виконано; SEC-002 в iteration 5 усуває targeted Vue/ws
advisories, але 6 High/1 Moderate residual entries мають окремий security follow-up.
Це локальна реалізація, не deployment або paid permission.
Батьківський документ: [ADR STAB-015](STAB-015-generation-execution.md).
Ці картки не є implementation або дозволом на runtime/DB/paid зміни.

Окремої чинної ADR/backlog ID convention у дослідженому baseline не знайдено;
використано стабільні sub-IDs STAB-015.01–.09 та leaf suffixes. Кожна leaf-картка
має один reviewable scope; **S** — вузький changeset, **M** — обмежений changeset
з integration tests. Це відносний розмір, не строк або зобов'язання реалізації.
Якщо M не вкладається в зрозумілий diff, її слід додатково розбити до початку роботи.

Позначення D1–D8, A01–A16, E01–E24 і T01–T13 посилаються на розділи 6, 12 та 14 ADR.
D1–D8 вже затверджені: повторно питати вибір A/B/C, одиницю cap, scope або SLO
не потрібно. P1–P8 ADR залишаються implementation/configuration параметрами.
Кожна implementation task призначається окремо; документація не дозволяє live
rollout. `.03a` — незалежний existing-contract fix. Історичні ownership/scope
п'яти задач iteration 3, включно зі STAB-003, збережено в [handoff](STAB-015-next-iteration.md).

**Не дублювати виконане:** STAB-007 disposable test harness, STAB-001 SDK retries=0
та structured quota classification, SAFE-001 global paid gate. STAB-004 уже
виправив CLI outcomes і None+missing worker mapping в інтеграційному
commit `900b4c2`; на його коді пройшли 397 backend tests. Ці fixes є
regressions для нових карток, а не відкритими задачами тут.

DB-backed tests запускає серійно один уповноважений інтегратор через
`bash scripts/backend-test.sh` за [testing-safety.md](../testing-safety.md).
Transport лише fake/MockTransport; no paid calls. Жодна картка не дозволяє
development/production DB writes або live rollout як спосіб перевірки.

## STAB-015.01 — рішення й контракт admission — COMPLETED

- **Проблема:** потрібен один авторитетний контракт після явного owner approval.
- **Scope:** Accepted D1–D8, current/future entrypoint matrix, unresolved parameters і узгоджений backlog/handoff; docs only.
- **Залежності:** виконано: явна owner instruction «STAB-015.01 — Accept Generation Execution Architecture ADR», задана дата рішення 2026-11-14; baseline PR #23.
- **Acceptance:** policy однозначна; current code не видається за future guarantees; на момент acceptance усі implementation cards були OPEN. D1–D8 не перепогоджуються.
- **Test strategy:** docs-only diff, links/anchors, consistency між ADR/backlog/state/architecture/safety docs і handoff; без DB/provider tests.
- **Ризики / розмір:** Accepted помилково прочитати як deployment або paid permission; **S**. Завершено лише decision contract.

## STAB-015.02a — additive execution та API-attempt ledger schema

**COMPLETED — iteration 4, 2026-11-15.** Additive revision
`0006_generation_ledger`: execution starts, append-only run links, paid-request
intent/reservation identities та outcome observations; без runtime writers або
legacy backfill. [P3 storage review, constraints і verification](../generation-ledger-schema.md).
P3 admission/locking/fencing protocol залишається залежністю відповідних наступних
карток; storage approval не завершує весь P3 і не дозволяє paid rollout.

- **Проблема:** mutable jobs/links не є immutable history або hard request-attempt ledger (E06/E11/E16).
- **Scope:** additive schema execution identity/start/origin/policy snapshot, per-request intent/reservation/outcome та зв'язків. Без runtime writer/admission switch.
- **Залежності:** completed .01; D2/D3/D4, P3 storage/retention design; збереження historical rows.
- **Acceptance:** execution start не підміняє counted API attempt; UTC admission identity immutable; старі IDs/history збережені, pre-cutover usage unknown. Nullable dev-diagnostic linkage не дає production direct exception.
- **Test strategy:** disposable migrations, uniqueness/FK/immutable timestamps, old-data upgrade без fabricated request counts.
- **Ризики / розмір:** misleading backfill, destructive downgrade; **M**. Не активує transport.

## STAB-015.02b — незмінна історія execution starts

**IMPLEMENTED — iteration 5, 2026-11-15; production activation blocked.**
Development/test claim + execution та direct execution + run/link записуються
атомарно; UUID replay перевіряє immutable snapshot. Caller-owned writes не
комітяться автономним lifecycle. Production execution залишається закритим;
справжній epoch уже надає .04a; atomic paid admission і решта safety chain pending.
[Контракт і інтегрована перевірка](../generation-execution-starts.md).

- **Проблема:** retry/reclaim повторно використовує або очищає job timestamps.
- **Scope:** execution-start records на claims та дозволені internal/dev paths, stable job/execution/run links; без підміни D2 cap цією одиницею.
- **Залежності:** .02a completed; D1/D2/D6. Production activation .02b додатково
  потребує справжнього epoch з .04a; не вигадувати epoch для проходження schema
  constraint. Це gate activation, не циклічна залежність реалізації .02b → .04a.
- **Acceptance:** retry/reclaim не стирають попередні execution IDs/links; claim/preflight denial відрізняється від paid request admission. A02.
- **Test strategy:** fake/stub executions, UTC rollover, denial, crash до/після start commit; не викликати provider.
- **Ризики / розмір:** подвійний start або пропущений caller; **M**. Request accounting завершують .02c/.03c.

## STAB-015.02c — durable request intent та unknown outcome

**INCREMENTAL IMPLEMENTATION VERIFIED — iteration 5, 2026-11-15.**
Transaction-owned intent/replay/observations і conservative evidence reader
реалізовані. Усі known paid transport paths безумовно закриті до atomic `.03c`;
SAFE-001, local permissions і production probe ban залишаються незалежними.
Production coordinator/runtime request admission **не реалізовано**; receipt не є
дозволом transport. Final atomic boundary і end-to-end dispatcher verification —
залежності `.03c`, не завершена гарантія цієї картки.
[Інтерфейси, fault tests та activation blockers](../request-intent-design.md).

- **Проблема:** attempt flush до provider не переживає crash/rollback; no-result не доводить not-sent.
- **Scope:** durable per-paid-request intent/phase protocol та outcome correlation. Перед transport intent і reservation мають спільну atomic boundary з .03c; поки її немає, paid rollout заборонений.
- **Залежності:** .02a/.02b; D2/D4; final SDK retry ownership і SAFE-001.
- **Acceptance:** однаковий durable intent без result перед/після transport → unknown / requires_review, без automatic retry/refund. Known pre-transport лише з protocol proof. Кожен дозволений retry має окрему identity; ledger не стирається. A07/A08.
- **Test strategy:** fault injection на всіх commit/transport boundaries, same-state conservative classification; dummy transport, no billing claims.
- **Ризики / розмір:** довгі transactions, хибний proof, lost outcome; **M**. Не exactly-once.

## STAB-015.02d — reliable usage та estimated cost

- **Проблема:** D2 usage/cost collection не реалізована нормалізовано; response payload не є повним billing ledger.
- **Scope:** надійні input/output usage metadata з provenance, model/pricing version і labeled monetary estimate. Hard money cap поза scope.
- **Залежності:** .02a/.02c; D2, P7 pricing/usage contract.
- **Acceptance:** missing/ambiguous usage unknown, не 0; estimates не називаються actual billing; unknown outcomes не refund; жодних reconstructed tokens з тексту або job count. A15.
- **Test strategy:** fake complete/partial/missing usage, unknown pricing/model, duplicate result, crash; decimal/units і redaction checks.
- **Ризики / розмір:** подвійний облік, outdated price, недовірений returned model; **M**. За потреби два послідовні commits: reliable usage ingestion → labeled pricing estimate.

## STAB-015.03a — exact-key conflict normalization

**COMPLETED — iteration 3, 2026-11-15.** Savepoint conflict normalization,
bounded winner-finalization handling та caller transaction preservation;
single/batch retry collisions покрито PostgreSQL regressions.
[Реалізація, межі та verification](../generation-job-deduplication.md).

- **Проблема:** чинний partial unique index відхиляє concurrent duplicate, але SELECT/INSERT loser може отримати необроблений IntegrityError (E05/E17).
- **Scope:** обробити лише conflict `uq_generation_jobs_active_dedupe_key`; reload/reuse або чинна validation error. Не змінювати dedupe key, index, scope чи architecture.
- **Залежності:** чинні schema/contracts; **не залежить від D1 або інших architecture cards**. Окреме task authorization потрібне; ADR не реалізує fix.
- **Acceptance:** `skip_duplicate=True` reuse existing active job; `False` зберігає validation rejection. `commit=False` не commit/rollback чужу transaction: savepoint/transaction ownership явно збережені. Unrelated IntegrityErrors propagate; якщо winner уже final, retry behavior bounded і визначене. A04.
- **Test strategy:** дві sessions з barrier перед INSERT; True/False × commit True/False; parent transaction з unrelated pending writes; unrelated constraint conflict; winner-finalizes race.
- **Ризики / розмір:** blanket exception swallowing, accidental outer rollback/commit, unbounded retry; **S** за чіткої existing constraint boundary.

## STAB-015.03b — атомарний package-level admission

**IMPLEMENTED — iteration 5, 2026-11-15.** Partial unique package index, short
transaction advisory lock, controlled busy outcomes та retry-helper admission
recheck. Managed history не звільняється автоматично за віком. Production
activation, paid cap і complete fencing залишаються blocked/pending.
[Контракт, migration та перевірки](../package-admission-design.md).

- **Проблема:** active-run SELECT і retry-cap count race; dedupe hashes не покривають overlapping jobs.
- **Scope:** DB-enforced exclusivity **date + locale + forecast_type** across providers/job types/direct/queue/subsets; controlled busy/deferred. Без sign-level parallelism або нового overwrite behavior.
- **Залежності:** .01/.02b; D3 accepted; P3 migration/locking contract, історичні overlaps перевірити без видалення.
- **Acceptance:** один active run на package; loser не робить paid request і не видає чужий running run за finished result. Published preserved, retries missing-only. A05.
- **Test strategy:** PostgreSQL independent sessions/barriers, overlap matrix, retry-cap race, already-published data; safe harness only.
- **Ризики / розмір:** broad lock, busy-contract compatibility; **M**. Якщо retry-cap serialization окрема — окремий commit; invariant D3 не послаблювати.

## STAB-015.03c — атомарний UTC-day paid API-attempt cap

- **Проблема:** job counts не дорівнюють requests, mutable timestamps і count-then-claim не дають hard cap.
- **Scope:** immutable counted reservation **кожної admitted paid provider request attempt**, включно retry; atomic intent+reservation до transport across authorized paths. Не hard monetary budget.
- **Залежності:** .02b/.02c/.03b; D2/D4; P1 числовий cap/configuration і P3 protocol. Missing/invalid cap не може означати unlimited paid operation.
- **Acceptance:** два contenders на останній slot допускають одну request attempt; UTC admission day, history збережена при manual retry/reclaim/crash; unknown без automatic refund; retry потребує нового slot. A02/A03.
- **Test strategy:** independent sessions, rollback/deadlock, UTC midnight, remaining cap при дозволеному retry, same unknown intent; proof-before-transport release окремо за P3.
- **Ризики / розмір:** hot counter/lock order, conservative overcount, double reservation; **M**. Live value не встановлювати в межах code task.

## STAB-015.04a — lease epoch та bounded heartbeat

**IMPLEMENTED FOUNDATION — iteration 5, 2026-11-15.** Revision 0008, monotonic
claim epoch, frozen owner/epoch/execution identity та explicit bounded renewal.
Timing default disabled; production timing/automatic renewal не активовані.
Historical positive execution epochs блокують migration до DDL, без fabricated
backfill. Позитивний epoch/ledger history не requeue за timestamp-only heuristic.
`.04b/.04c` ще потрібні для всіх publication/finalization writes: це не complete
fencing і не дозволяє automatic paid reclaim. P2 вимірювання/операційні values
залишаються pending. [Контракт і перевірка](../lease-epoch-design.md).

- **Проблема:** `locked_by` і timestamp не відрізняють старий execution від нового; TTL не вимірює progress.
- **Scope:** additive epoch/lease fields, claim/renew protocol та fake-clock tests; не активувати новий automatic reclaim або заявляти end-to-end fencing.
- **Залежності:** .01/.02b, D4; max duration/heartbeat policy.
- **Acceptance:** reclaim видає новий epoch; повтор worker ID не оживляє старий lease; renew only-current-owner; duration і heartbeat окремі.
- **Test strategy:** two-session claim/renew, fake clock, process restart/same worker ID, renew-expire boundary.
- **Ризики / розмір:** heartbeat false positives, DB pressure, interval без measured duration; **M**. Частковий протокол не є безпечним fencing.

## STAB-015.04b — fencing forecast/item/attempt writes

- **Проблема:** старий owner може завершити provider call і publish після lease loss (E02/E08/E15).
- **Scope:** epoch-aware conditional writes для forecast та відповідних item/attempt outcomes, trusted execution context; зберегти final publication guard.
- **Залежності:** .04a/.02c; D4; audit усіх writer paths цих сутностей.
- **Acceptance:** stale owner не overwrite/publish і не привласнює current outcome; remote response може бути записаний лише як fenced/uncertain evidence за погодженим contract, не success нового execution.
- **Test strategy:** freeze old owner перед save, reclaim, new owner progress, resume old owner; existing forecast + new INSERT cases; publication-policy regressions.
- **Ризики / розмір:** unfenced generic persistence helper, помилкове стирання evidence; **M**. Auto-reclaim лишається gated до .04c/.05b.

## STAB-015.04c — fencing решти transitions

- **Проблема:** run/job finalize, exception handler, stale closer, retry/cancel можуть перезаписати новий state без CAS (E03/E07/E08/E11).
- **Scope:** conditional run/job transitions і retry/cancel conflict results; повний writer inventory з .04b, без нового running-cancel promise.
- **Залежності:** .04a/.04b/.03a/.03b; D4.
- **Acceptance:** old owner/old exception handler/reaper не завершують новий execution; cancel-before-claim не виконується; retry conflict детермінований. **Fencing safe лише після покриття всіх writers**, включно з errors/cleanup/helpers. A06/A10.
- **Test strategy:** barriers для finish/reaper, claim/cancel, retry/new-duplicate, old-owner exception; negative coverage inventory.
- **Ризики / розмір:** missed writer, changing client-visible conflicts, nested transactions; **M**. За потреби розділити transitions на додаткові leaf commits.

## STAB-015.05a — read-only per-job recovery inspection

**COMPLETED — iteration 3, 2026-11-15.** Bounded read-only CLI одного job,
shared snapshot/coverage, explicit unknown evidence та sanitized startup.
[Контракт і regression evidence](../generation-recovery-inspection.md).

- **Проблема:** один job/run/content може мати розбіжні states без пояснюваної history.
- **Scope:** bounded report **конкретного job ID**: owner/timestamps/run link, item/attempt status summaries, published/missing scope, missing evidence/unknown. Не aggregate dashboard, refund/requeue або нова schema.
- **Залежності:** чинні read contracts; .01 completed. Не потребує ledger/fencing. Proposed module/CLI boundary — [handoff](STAB-015-next-iteration.md).
- **Acceptance:** SELECT-only; stale timestamp не доказ смерті worker, legacy missing intent не known-not-sent; published-but-not-finalized і missing links видимі. No raw secret/prompt/response exposure; no operational mutation.
- **Test strategy:** disposable divergent per-job fixtures, query-only enforcement, provider/commit prohibition, deterministic CLI reports. Aggregate deadlines/queue trends належать .07b.
- **Ризики / розмір:** хибний recovery advice з неповного audit; **S**. Read authority не recovery authority.

## STAB-015.05b — консервативні recovery mutations

- **Проблема:** crash може залишити unknown remote outcome або published-but-not-finalized work.
- **Scope:** D4 bounded reconciliation зі збереженням published content; automatic recovery лише durable proof transport-not-reached; authorized audited manual review.
- **Залежності:** .05a/.02c/.03c/.04c; D4 accepted; P3 transition representation і P5 operator authority.
- **Acceptance:** intent/no-outcome → unknown / requires_review, без automatic retry/refund; proof не підміняється lease expiry. Historical published rows не overwrite. Manual decisions audited; replay не обходить D2/D5. A07–A10.
- **Test strategy:** crash matrix, stale-owner responses, same-state ambiguity, published-before-finalization, unauthorized manual recovery rejection.
- **Ризики / розмір:** accumulated review queue, lost evidence, false proof; **M**. Не exactly-once або provider-side retrieval promise.

## STAB-015.06a — quota/auth/permission pause між executions

- **Проблема:** STAB-001 quota permanent лише для item; future items/runs можуть повторювати paid failures.
- **Scope:** structured insufficient_quota → provider/account-scoped pause; auth/permission failures, що потребують operator intervention, блокують automatic admission у відповідному scope. Authorized audited resume, без automatic cooldown-resume.
- **Залежності:** .01/.03c; D5 accepted; P1 logical scope identity, P5 operator authority.
- **Acceptance:** pause перевіряється до кожного нового paid request, включно іншими items/runs/processes; transient не стає permanent за message heuristic. SDK retries=0 і quota nonretryable збережені; старі lifecycle counts оновлюються для D5 навмисно. A11.
- **Test strategy:** fake quota/auth/permission, concurrent pause/admission, cross-process observation, explicit unauthorized/authorized resume; no live traffic.
- **Ризики / розмір:** overbroad scope, hidden self-resume, credentials leakage; **M**. Не повторна реалізація STAB-001 classifier.

## STAB-015.06b — limited safe transient retry за D5

- **Проблема:** current retryable boolean широко допускає 429/timeout/connection/validation до 3 attempts і не доводить safe replay.
- **Scope:** reliable phase/outcome classification; confirmed safe transient rate-limit — максимум **одна додаткова application-level attempt**, bounded backoff/Retry-After/deadline. Unknown не повторювати; connection лише proof transport-not-reached; text validation не створює paid retry за замовчуванням.
- **Залежності:** .02c/.03c/.04c/.06a; D5 accepted; P2 measured delay/deadline protocol.
- **Acceptance:** кожен retry з новою D2 reservation; no hidden SDK retries, no reset retry budget через requeue; lease/gate/pause/deadline/cap rechecked. Не всі 429/timeout/connection failures safely retryable. A11.
- **Test strategy:** fake safe/ambiguous 429, seconds/date Retry-After, timeout після remote acceptance, proven local pre-transport failure, validation rejection, exhausted cap, lease loss; fake clock, no sleeps.
- **Ризики / розмір:** message-based proof, duplicated requests, hidden retry multiplication; **M**. Розбити на два commits за потреби: evidence/outcome normalization → lifecycle admission/backoff orchestration. SDK/quota regressions зберегти; old three-attempt expectations змінити лише за D5.

## STAB-015.07a — базова DB readiness

**COMPLETED — iteration 3, 2026-11-15.** Additive `/health/ready`, independent
read-only PostgreSQL probe та exact Alembic-head comparison, sanitized 200/503.
Server/connection timeouts не є strict total DNS/HTTP deadline; production polling
і outer deadlines залишаються operational policy.
[Контракт, межі та verification](../database-readiness.md).

- **Проблема:** static /api/signs health response не доводить DB readiness.
- **Scope:** bounded read-only DB SELECT + expected schema readiness окремо від API liveness; без migrations, heartbeat або ledger. Новий endpoint contract інтегрує orchestrator.
- **Залежності:** .01 completed; [handoff](STAB-015-next-iteration.md) endpoint/budget contract. Не потребує .02/.03/.04.
- **Acceptance:** API alive/DB down та ready відрізняються; ready не означає worker progress, quota або 06:00 coverage. Response sanitized, жодних provider calls/writes. A13.
- **Test strategy:** DB failure/timeout/schema mismatch, read-only transaction, no credentials in response; isolated fixtures/mock failures.
- **Ризики / розмір:** probe load/restart loops, leaked connection details; **S**. Live Compose healthcheck не перемикається автоматично.

## STAB-015.07b — aggregate coverage/queue та deadline visibility

**COMPLETED — iteration 3, 2026-11-15.** Bounded local read-only CLI з shared
coverage, today/tomorrow, 06:00 Kyiv, queue age/counts та explicit unknown causes.
79 operations/cross-report/redaction/startup regressions пройшли через disposable
harness. [Контракт і межі](../generation-operations.md). Alert transport, durable
historical SLO evidence, heartbeat/pause/cost reasons лишаються поза цим scope.

- **Проблема:** success job/no-work exit не доводить complete current-day coverage або D8 SLO.
- **Scope:** aggregate date/locale/type coverage enabled signs, queue depth/oldest age, last observed run status; 06:00 Europe/Kyiv deadline evaluation. Не per-job recovery report (.05a), pause implementation або нові ledger fields.
- **Залежності:** .01 completed, D8 accepted; existing DB read data і [handoff](STAB-015-next-iteration.md). Не залежить від .02/.04/.06a; channel/alert routing пізніше P5.
- **Acceptance:** missing/partial після deadline → actionable structured failure; published content збережено. Expected count з enabled rows, нуль не замінюється 13. Liveness/readiness/worker evidence/content deadline різні; відсутній heartbeat/pause evidence — unknown/not implemented, не fabricated cause. Пізня full coverage не доводить historical on-time completion. A12/A13/A16.
- **Test strategy:** 05:59:59/06:00/after, winter/summer UTC offsets, dynamic enabled signs/zero case, queue with zero processed, partial content; SELECT-only, no raw payload.
- **Ризики / розмір:** false-green freshness, inferred root cause, cardinality; **S**. Concrete notification transport поза scope.

## STAB-015.07c — execution та recovery diagnostics

- **Проблема:** нові reservations/leases/pauses/unknown outcomes потребують причин і correlation.
- **Scope:** bounded diagnostics counted API attempts/remaining cap, lease/worker progress, quota/auth/permission pause, unknown review queue та D8 deadline reasons; usage estimates labeled окремо.
- **Залежності:** .07a/.07b/.02d/.03c/.04c/.06a; D8, P5 routing/retention.
- **Acceptance:** quota pause, worker failure, missed deadline та cap exhaustion не змішуються; no-work не приховує missing content. API counts не money spend; partial historical evidence unknown.
- **Test strategy:** fake clocks/reason codes, UTC admission vs Kyiv deadline, paused worker/quota and partial coverage, redaction.
- **Ризики / розмір:** misleading budget labels/alert fatigue; **S**. Dashboard framework не потрібен.

## STAB-015.08a — явний async compatibility contract

- **Проблема:** regular production generation має стати async без silent replacement sync run response/exit semantics.
- **Scope:** additive/versioned API або explicit CLI mode: enqueue/job ID/status/results; deprecation/migration синхронних callers. Local stub direct зберегти.
- **Залежності:** .01 completed; D1/D6 accepted; P4 конкретний envelope/endpoint/window.
- **Acceptance:** queued intent не видається за completed run; old synchronous contract не мовчки змінений; production paid direct disabled by default. STAB-004 failure/no-work semantics збережені там, де sync/worker command лишається.
- **Test strategy:** old/new contract fixtures, CLI main/__main__, enqueue accepted vs execution failed/partial/busy; mocks only.
- **Ризики / розмір:** ambiguous CLI success, endless deprecation tail; **M**. Не paid activation.

## STAB-015.08b — обов'язкова keyless producer authorization migration

- **Проблема:** common Admin parser зараз вимагає OpenAI key навіть для enqueue.
- **Scope:** separate enqueue authorization і execution credentials; зберегти admin enable/token/allow/request confirmation. Backend/Admin та scheduler producer більше не потребують key для enqueue; execution checks у worker. Фактичне вилучення key references із production roles належить .08e, live secrets migration — .09.
- **Залежності:** .08a/.03c; D7 accepted, не conditional. Має бути завершено до .08e production credential topology та .08d rollout.
- **Acceptance:** authorized keyless producer enqueue працює, unauthorized ні; worker без key/global/local/admission/publication permission відмовляє. No key forwarding у payload; legacy paid direct API explicit denied/migrated.
- **Test strategy:** producer/executor auth matrix з dummy key, missing key, global denied, publication denied, local stub; public read contracts.
- **Ризики / розмір:** weakening enqueue auth, mistaken consent-to-spend; **S**. Secrets migration лише .09.

## STAB-015.08c — production probe ban і bounded dev diagnostics

**PARTIAL:** .08c-A completed в iteration 4; .08c-B OPEN. Повна .08c не завершена.

- **Початкова проблема:** probe мав global guard без production ban або bounded audited request accounting. .08c-A закриває ban; accounting лишається .08c-B.
- **Scope:** **заборонити paid probe в production** main/helper незалежно від global=1; dev diagnostics explicit authorization + SAFE-001 + bounded auditable API-attempt admission. Diagnostic output не publish; read-only listing зберегти.
- **Залежності:** D6 accepted; production-denial частина незалежна від нового ledger; dev transport enablement потребує .02c/.03c та визначеного dev cap/authority. Повна .08c обов'язкова до .08d, або dev transport залишається explicitly disabled до її завершення.
- **Acceptance:** немає production diagnostic exception; direct helper не обходить denial/accounting; SDK retry behavior не приховує uncapped attempts. Unknown не auto-replay/refund. A14.
- **Test strategy:** fake SDK/MockTransport, production deny even enabled global, read-only listing, dev auth/gate/cap matrix і audited request counts; жодного live probe.
- **Ризики / розмір:** untracked dev requests, accidental production exception; **M**. Два reviewable commits: production ban → bounded dev admission; не лишати enabled unaccounted проміжний стан.

### STAB-015.08c-A — production probe prohibition — COMPLETED

- **Scope / result:** CLI main і direct helper забороняють production paid probe
  незалежно від SAFE-001=1; missing/invalid process mode fail-closed. Listing
  пропускає dotenv/SDK; незалежний global gate збережений.
- **Evidence:** [probe contract і tests](../production-probe-policy.md), integrated
  [checkpoint](../CURRENT_STATE.md). Немає runtime paid enablement.

### STAB-015.08c-B — bounded audited development diagnostics — OPEN

- **Problem / scope:** retained dev path не має per-request ledger/cap, explicit
  diagnostic authority або узгоджених SDK retry guarantees. Додати bounded dev
  admission без production exception або automatic publication.
- **Dependencies:** .02c/.03c, P1 dev admission scope/cap і P5 authority; .08c-A
  already completed. Новий storage .02a сам не дозволяє transport.
- **Acceptance:** кожен dev paid request/retry проходить explicit authorization,
  SAFE-001 та counted reservation; unknown не replay/refund; direct helper не bypass.
- **Tests / risk:** fake SDK/MockTransport, cap/authority/deny/unknown matrix;
  ризик hidden SDK requests. **M**, відокремити retry-ownership підкрок за потреби.
- **Interim rule:** зберігати реальні diagnostics disabled до завершення .08c-B.
  Кодова сумісність development/test з independent global gate не є authorization.

## STAB-015.08e — ізоляція producer/worker credential environments

- **Проблема:** нинішній scheduler process може і produce, і execute; Compose передає key також backend.
- **Scope:** окремі process/service roles для одного producer та одного worker; production configuration mapping без key у backend/Admin/producer. Development defaults окремо; без live recreate/secrets changes.
- **Залежності:** .08b/.04c; D7, P8 measured role/startup/deployment design. Спільний process із key не є worker-only isolation.
- **Acceptance:** sanitized rendered production config містить key reference лише worker; worker restart не запускає producer/direct startup generation; role identities/default deny явні.
- **Test strategy:** static config rendering, startup/role mocks, dummy env inventory; ніяких live keys або запуска scheduler.
- **Ризики / розмір:** два workers при deploy, accidental direct startup; **M**. За потреби окремі commits role entrypoints → production config wiring; застосування лише .09.

## STAB-015.08f — date priority та bounded backfill fairness

- **Проблема:** чинні numeric priorities не забезпечують today→tomorrow→backfill та anti-starvation при business-date rollover.
- **Scope:** date-aware queue selection/producer priority policy і bounded fairness, без зміни D2 cap/D3 scope або publication overwrite.
- **Залежності:** .03c/.07b; D8, P6 measured capacity/fairness parameters.
- **Acceptance:** current-day deadline має пріоритет; historical work не голодує за достатньої admission capacity. Якщо cap/capacity несумісні з обома вимогами — actionable capacity/starvation signal, не overspend або fabricated content.
- **Test strategy:** fake Kyiv dates/rollover, backlog arrivals, bounded serving opportunity, exhausted cap/current-day missing; no real generation.
- **Ризики / розмір:** starvation або deadline regression; **S** після P6. Initial topology лишається one-worker.

## STAB-015.08d — production queue default і direct restriction

- **Проблема:** D1 queue-first і D7 worker-only ще не реалізовані; сам toggle не закриває correctness/cost gaps.
- **Scope:** production callers dispatch через queue; restrict paid direct/internal adapter bypass; cheap local stub зберегти. Без live activation.
- **Залежності:** .02a/.02b/.02c/.02d, .03b/.03c, .04a/.04b/.04c, .05b, .06a/.06b, .07a/.07b/.07c, .08a/.08b/.08c/.08e/.08f. D1–D8 Accepted; .08b і production probe ban не N/A.
- **Acceptance:** all entrypoints obey ADR §6.2; every paid request admitted/counted; no stale writes/unknown replay; async compatibility явна; public GET read-only; defaults не вмикають paid generation.
- **Test strategy:** full entrypoint/role/permission matrix, crash/concurrency/denial/rollover/SLO regressions через safe harness, static production config; no deployment.
- **Ризики / розмір:** stranded jobs/old binary bypass; **M**. Не пропускати ledger/fencing/recovery prerequisites заради раннього default switch.

## STAB-015.09 — окремо погоджений rollout і rollback runbook

- **Проблема:** Accepted policy/code/config не доводять effective production runtime або secrets isolation.
- **Scope:** runbook one producer/one worker/PostgreSQL/keyless API; stop-admission/drain/reconcile, effective settings, readiness/06:00 coverage, secrets migration/rollback. Documentation, не deployment.
- **Залежності:** .08d, P1–P8 необхідні concrete values; окрема operator approval на live rollout, secret migration та paid enablement.
- **Acceptance:** verified role credentials без secret output; scheduler не запускається як smoke test; unknown не replay/refund; rollback зберігає history і не повертає unrestricted direct binary. Hard money budget/broker не prerequisites.
- **Test strategy:** tabletop + isolated sanitized config/fake-provider rehearsal; actual rollout поза code-task permission.
- **Ризики / розмір:** mixed versions/overlap/stale env/audit loss; **S** як runbook.

## Послідовні checkpoints

1. **Decision contract completed:** .01; implementation не виконувалася.
2. **Незалежні fixes/visibility:** .03a, .05a, .07a, .07b та STAB-003 за
   [next-iteration handoff](STAB-015-next-iteration.md). Backend DB suites лише
   серійно, frontend toolchain — окремий scope. Paid gate лишається denied.
3. **Immutable accounting та invariants:** .02a–.02d, .03b/.03c і .04a–.04c за
   dependencies. Кожен commit має safe regressions; partial fencing не rollout-ready.
4. **Conservative operation:** .05b, .06a/.06b, .07c; safe fake crash/retry rehearsal.
5. **Async/keyless production:** .08a/.08b/.08c/.08e/.08f → .08d → .09. Немає
   conditional skip для worker-only key або production probe ban; runtime і paid
   activation окремо погоджуються.

Existing IDs збережені; .02d, .08e і .08f — відсутні раніше окремі обов'язкові
роботи для usage/cost, role isolation і D8 fairness, а не дублікати завершених
safety fixes. .06b і .08c потребують послідовних невеликих commits як зазначено
в scope. Числовий cap, TTL/deadlines та operational routing не обрані довільно.
Немає залежності від prerender/Ollama/Redis/Celery. Hard monetary budget і
sign-level parallelism deferred; historical published data зберігаються.
