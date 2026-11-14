# STAB-015: запропонований backlog виконання генерації

**Proposed / Pending owner approval — 2026-11-14.**
Батьківський документ: [ADR STAB-015](STAB-015-generation-execution.md).
Ці картки не є implementation або дозволом на runtime/DB/paid зміни.

Окремої чинної ADR/backlog ID convention у дослідженому baseline не знайдено;
використано стабільні sub-IDs STAB-015.01–.09 та leaf suffixes. Кожна leaf-картка
має один reviewable scope; **S** — вузький changeset, **M** — обмежений changeset
з integration tests. Це відносний розмір, не строк або зобов'язання реалізації.
Якщо M не вкладається в зрозумілий diff, її слід додатково розбити до початку роботи.

Позначення D1–D8, A01–A14, E01–E24 і T01–T13 посилаються на розділи 6, 12 та 14 ADR.
Implementation залежних архітектурних карток починається лише після відповідних
owner decisions. `.03a` є потенційно незалежним bugfix на чинному контракті;
для нього не потрібен вибір A/B/C, але потрібне окреме призначення задачі.

**Не дублювати виконане:** STAB-007 disposable test harness, STAB-001 SDK retries=0
та structured quota classification, SAFE-001 global paid gate. STAB-004 уже
виправив CLI outcomes і None+missing worker mapping в інтеграційному
commit `900b4c2`; на його коді пройшли 397 backend tests. Ці fixes є
regressions для нових карток, а не відкритими задачами тут.

DB-backed tests запускає серійно один уповноважений інтегратор через
`bash scripts/backend-test.sh` за [testing-safety.md](../testing-safety.md).
Transport лише fake/MockTransport; no paid calls. Жодна картка не дозволяє
development/production DB writes або live rollout як спосіб перевірки.

## STAB-015.01 — рішення й контракт admission

- **Проблема:** A/B/C, одиниця ліміту, scope і uncertain-outcome policy не затверджені.
- **Scope:** записати D1–D8, state/outcome vocabulary, перелік дозволених callers; без коду/config/schema.
- **Залежності:** owner answers; E01–E24; реалізований STAB-004.
- **Acceptance:** для кожного caller визначено enqueue/execution/publication authorization, sync/async response та recovery owner; unknown не прирівнюється до not-sent.
- **Test strategy:** review таблиці всіх entrypoints і A01–A14 на несуперечність, посилання на чинні contracts.
- **Ризики / розмір:** непомітне прийняття money budget або paid permission; **S**. Pending.

## STAB-015.02a — additive execution ledger schema

- **Проблема:** job timestamps і `run_id` mutable; немає незмінної історії starts (E06/E11/E16).
- **Scope:** additive Alembic schema для execution identity/start/origin/policy snapshot та зв'язків; без runtime writer або зміни admission.
- **Залежності:** .01, D2/D3; retention та historical import policy.
- **Acceptance:** timestamps starts незмінні; nullable direct job link узгоджений; старі rows/IDs збережені; history до cutover позначена incomplete, не синтезована як точні starts.
- **Test strategy:** disposable migration/schema tests, nullable/unique/FK/retention semantics; old-data fixture upgrade без реконструкції HTTP counts.
- **Ризики / розмір:** misleading backfill, schema downgrade з втратою audit; **M**. Без runtime switch.

## STAB-015.02b — запис кожного execution start

- **Проблема:** retry/reclaim стирає або повторно використовує daily timestamp; один job не дорівнює одному execution.
- **Scope:** wire execution-start records на claim та погоджені direct admissions, stable job/execution/run links; read-only count comparison. Старий policy switch не змінювати тут.
- **Залежності:** .02a; .01 перелік callers та D2 одиниця starts.
- **Acceptance:** manual single/batch retry і stale reclaim створюють нові execution IDs; denial-before-provider окремо від HTTP attempts; old execution links не стираються; coverage A02.
- **Test strategy:** stub/fake runs, retry across UTC midnight, preflight denial, failure перед/після start commit; перевірити прямі helpers.
- **Ризики / розмір:** подвійний запис або пропущений direct caller; **M**. Новий ledger ще не дає atomic cap.

## STAB-015.02c — durable attempt intent та unknown outcome

- **Проблема:** attempt flush перед provider не переживає rollback/crash (E02); audit може втратити факт наміру.
- **Scope:** короткий commit наміру перед transport, correlation/request identity, outcome recording; окремий документований transport protocol. Без auto-retry/refund recovery.
- **Залежності:** .02a/.02b, D2/D4; збереження STAB-001 і SAFE-001.
- **Acceptance:** intent durable; **intent без result не доводить sent/not-sent**. Crash безпосередньо до/після transport з однаковим durable state → unknown; pre-transport лише за protocol proof недосяжності transport. A07/A08.
- **Test strategy:** deterministic fault injection у кожній commit/transport boundary; однакові DB states дають однакову conservative classification; no fake billing claims.
- **Ризики / розмір:** зайві commits, довгі transactions, помилковий refund; **M**. Не дає exactly-once.

## STAB-015.03a — exact-key conflict normalization

- **Проблема:** чинний partial unique index відхиляє concurrent duplicate, але SELECT/INSERT loser може отримати необроблений IntegrityError (E05/E17).
- **Scope:** обробити лише conflict `uq_generation_jobs_active_dedupe_key`; reload/reuse або чинна validation error. Не змінювати dedupe key, index, scope чи architecture.
- **Залежності:** чинні schema/contracts; **не залежить від D1 або інших architecture cards**. Окреме task authorization потрібне; ADR не реалізує fix.
- **Acceptance:** `skip_duplicate=True` reuse existing active job; `False` зберігає validation rejection. `commit=False` не commit/rollback чужу transaction: savepoint/transaction ownership явно збережені. Unrelated IntegrityErrors propagate; якщо winner уже final, retry behavior bounded і визначене. A04.
- **Test strategy:** дві sessions з barrier перед INSERT; True/False × commit True/False; parent transaction з unrelated pending writes; unrelated constraint conflict; winner-finalizes race.
- **Ризики / розмір:** blanket exception swallowing, accidental outer rollback/commit, unbounded retry; **S** за чіткої existing constraint boundary.

## STAB-015.03b — атомарний scope admission

- **Проблема:** exact-key dedupe не покриває overlap; active-run SELECT і retry-cap count не атомарні (E02/E03/E05).
- **Scope:** DB-enforced reservation для погодженого D3 scope і retry-run admission; normalize busy outcome. Не змінювати count-budget policy або lease recovery.
- **Залежності:** .01, .02b, D3; plan для existing overlapping rows без їх мовчазного видалення.
- **Acceptance:** direct+queue/rізні job types/providers/subsets не створюють паралельний admitted scope всупереч D3; existing running run не називається завершеним caller result. A05.
- **Test strategy:** independent PostgreSQL sessions, concurrent retries на останньому дозволеному run, overlap matrix; no provider calls у loser.
- **Ризики / розмір:** надто широкий lock, starvation, compatibility busy outcome; **M**. Якщо scope і retry-cap потребують різних mechanisms — окремі commits до review.

## STAB-015.03c — атомарна count reservation

- **Проблема:** daily count-then-claim дозволяє oversubscription між workers (E06).
- **Scope:** атомарний reservation погодженої D2 count unit/window з ledger; застосувати до всіх дозволених execution paths. Не впроваджувати hard money budget.
- **Залежності:** .02b/.02c, .03b, D2/D4; bounded transaction protocol.
- **Acceptance:** два contenders на останній slot допускають одного; UTC rollover і ручний retry не стирають usage; unknown не refund автоматично. A02/A03.
- **Test strategy:** PostgreSQL barriers, commit failure/deadlock retry, midnight, reserved-but-never-started та uncertain outcomes; count views узгоджені.
- **Ризики / розмір:** hot counter row, lock ordering, conservative overcount; **M**. Tokens/money — окрема owner-approved задача за потреби.

## STAB-015.04a — lease epoch та bounded heartbeat

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

## STAB-015.05a — read-only inspection для recovery

- **Проблема:** оператору важко зіставити jobs, runs і published coverage перед будь-яким повтором або cleanup.
- **Scope:** bounded read-only report поточних status/owner/timestamps/run links/coverage; явні позначки missing evidence та unknown. Без requeue, refund, provider calls або нового schema.
- **Залежності:** чинні read contracts; окреме погодження формату звіту. Не потребує ledger, lease redesign або вибору A/B/C; нові поля .02/.04 можна додати пізніше.
- **Acceptance:** report не змінює дані; старі rows без durable intent не називаються known-not-sent; stale timestamp не доводить, що worker помер; published-but-not-finalized і missing scope видимі окремо.
- **Test strategy:** disposable fixtures з divergent job/run/content states, відсутніми links, stale/unknown та complete coverage; заборонити commit і provider у read path.
- **Ризики / розмір:** помилкова впевненість у historical metadata, exposed payload/secrets; **S**. Це inspection, не дозвіл на recovery mutation.

## STAB-015.05b — консервативні recovery mutations

- **Проблема:** crashes залишають розбіжність job/run/content; невідомий remote outcome небезпечно повторювати.
- **Scope:** bounded reconciliation для durable phases, published-but-not-finalized, stale ownership та unknown; operator inspection/decision path. Без provider-side exactly-once claim.
- **Залежності:** .05a/.02c/.03c/.04c, D4; provider idempotency/retrieval перевірити окремо перед використанням.
- **Acceptance:** A07–A09; same intent/no-result crash windows лишаються unknown; немає auto-refund/retry без достатнього доказу; published skip не робить provider call; manual decisions audited.
- **Test strategy:** deterministic crash matrix, PostgreSQL transaction failures, no-result/late-result fake provider; unknown і proven pre-transport cases окремо.
- **Ризики / розмір:** manual queue accumulation, помилкова reconciliation, latency; **M**. Лише погоджені bounded mutations; inspection залишається окремою .05a.

## STAB-015.06a — cross-run quota pause

- **Проблема:** STAB-001 зупиняє лише item retry; future items/runs можуть повторити permanent quota failure.
- **Scope:** structured failure reason, погоджений provider/account policy scope, pause/resume/cooldown; не розширювати permanent-code allowlist за message heuristics.
- **Залежності:** .01/.03c, D5; failure-classification compatibility та operator owner.
- **Acceptance:** підтверджена quota зупиняє подальший admission у погодженому scope; resume audited; transient errors не стають permanent; STAB-001 tests незмінно проходять. A11.
- **Test strategy:** fake quota across items/runs/processes, concurrent pause/admission, explicit resume, no paid traffic.
- **Ризики / розмір:** надмірний global pause, endless suppression, необґрунтована account identity; **M**. Не повторна реалізація STAB-001.

## STAB-015.06b — bounded transient retry policy

- **Проблема:** lifecycle loop retryable errors не має backoff/deadline policy.
- **Scope:** погоджені bounded delay/jitter/deadline для lifecycle retries; SDK retries залишаються 0; attempt numbering/audit збережені.
- **Залежності:** .01/.02c, D5; узгодження з .04a lease duration.
- **Acceptance:** transient attempts bounded, quota не retryable, cancellation/lease loss не запускають нову спробу; fake time не затримує tests. A11.
- **Test strategy:** deterministic clock/random injection, transient 429/timeout/validation, deadline, gate/lease loss між attempts.
- **Ризики / розмір:** довгий job, hidden retry amplification, test sleeps; **S** після погодження policy.

## STAB-015.07a — базова DB readiness

- **Проблема:** static `/api/signs` response не доводить DB readiness або scheduler/worker progress.
- **Scope:** read-only bounded SELECT та expected schema readiness окремо від чинної API liveness; без worker heartbeat, ledger або execution metrics.
- **Залежності:** погоджений endpoint/операційний контракт readiness. Не залежить від .01, .02, .03 або .04; D8 може пізніше визначити alert thresholds.
- **Acceptance:** API up/DB down і API/DB ready розрізняються; readiness не стверджує worker progress/content freshness; жодних provider calls/migrations/writes у health probe. Базова частина A13.
- **Test strategy:** DB failure/timeouts mocks і disposable integration, schema mismatch, redaction tests.
- **Ризики / розмір:** health amplification, leaking configuration/secrets, restart loop; **S**. Не змінює publication freshness.

## STAB-015.07b — базова coverage та queue visibility

- **Проблема:** CLI zero-work success і job success не доводять content freshness; count/quota/denial причини змішані.
- **Scope:** read-only existing business-date coverage/missing/partial views, queued depth/oldest age та останній відомий run status; без нових reservation/quota/lease fields.
- **Залежності:** погоджений bounded output scope; чинні public/admin read contracts. Не залежить від ledger, fencing або quota-pause implementation; thresholds/freshness SLO окремо D8. Не змінювати empty enabled-sign policy мовчки.
- **Acceptance:** active metadata scope, UTC timestamps і business timezone розділені; job/run success не підміняє actual coverage; missing worker evidence позначено unknown; no secrets/raw payload metrics. Базова частина A12/A13.
- **Test strategy:** zero/partial/full active-sign coverage, midnight/DST, zero processed jobs із непорожньою queue, backlog age; no writes/provider calls.
- **Ризики / розмір:** high-cardinality labels, хибне «fresh» для old published data; **S**. Наявність published content і його product freshness — різні сигнали.

## STAB-015.07c — execution та recovery diagnostics

- **Проблема:** нові reservations, leases, quota pause та unknown outcomes потребуватимуть власних пояснюваних сигналів.
- **Scope:** bounded read-only diagnostics для admission/denial/remaining slots, heartbeat/lease health, pause reason та uncertain outcomes; кореляція без raw payload.
- **Залежності:** .07a/.07b та реалізовані .02b/.03c/.04a/.06a; D8. Кожен сигнал додається разом із відповідним mechanism, без вигаданих historical counts.
- **Acceptance:** local limit, quota pause, disabled paid gate, stale lease й unknown remote result не змішуються; no-work exit не приховує blocked coverage; liveness/readiness/freshness окремі. Решта A13.
- **Test strategy:** fake clock і disposable fixtures для всіх reason codes, absent historical fields, rollover, redaction та cardinality bounds.
- **Ризики / розмір:** alert fatigue, misleading budget labels, credentials у logs; **S** для погоджених bounded diagnostics, без dashboard framework.

## STAB-015.08a — caller compatibility contract

- **Проблема:** default enqueue може зламати синхронні Admin/CLI clients.
- **Scope:** additive async request/response/status contract та deprecation window; зберегти STAB-004 exit semantics; без default switch.
- **Залежності:** .01, D1/D6; existing Admin/job APIs.
- **Acceptance:** queued intent не маскується як completed run; explicit async selection; old paths працюють за затвердженою policy; empty batch `0` не обіцяє drained queue.
- **Test strategy:** contract snapshots, CLI main/__main__, sync/async/no-work/busy/failed/partial; no provider transport.
- **Ризики / розмір:** shell automation break, ambiguous exit codes, indefinite compatibility tail; **M**.

## STAB-015.08b — producer authorization і key boundary

- **Проблема:** Admin common queue parser зараз вимагає API key для enqueue; простий key removal ламає workflow (E10).
- **Scope:** відокремити enqueue authorization від execution credentials, зберегти admin enable/token/allow/request confirmation; immediate paid API у keyless process explicit deny/migrate.
- **Залежності:** .01/.08a, D7; shared execution guards .03c, policy щодо direct exceptions.
- **Acceptance:** authorized keyless producer може enqueue; unauthorized не може; worker без key/global/local approval не виконує; no credential forwarding у job payload. A14.
- **Test strategy:** full producer/executor auth matrix, missing key, global denied, production policy denied, explicit stub; dummy credentials only.
- **Ризики / розмір:** accidental authorization weakening, direct path bypass, confusing creation approval with spend; **S** для обмеженого parser/policy diff.

## STAB-015.08c — standalone probe policy

- **Проблема:** probe поза lifecycle ledger/counts і має власні SDK retry defaults.
- **Scope:** реалізувати погоджений D6 diagnostic-exception або shared-admission contract; не перетворювати probe на production publisher.
- **Залежності:** .01/.02c/.03c, D6/D7; explicit transport/retry ownership.
- **Acceptance:** paid gate незмінний, listing read-only; diagnostic requests обліковуються згідно D2 або явно обмежені погодженим exception; не заявляти adapter one-request semantics без відповідного change/test.
- **Test strategy:** fake SDK/MockTransport, direct helper/main, denial-before-client, listing, request counts; no live probe.
- **Ризики / розмір:** untracked bypass або втрата простого diagnostic workflow; **S** після чіткого owner choice.

## STAB-015.08d — queue default і direct restriction

- **Проблема:** обидва шляхи нині штатні; one-worker policy не прибирає direct helpers або ручний worker.
- **Scope:** переключити погоджені callers на queue за D1; restrict direct execution включно з внутрішніми helpers; зберегти cheap local stub. Без live activation.
- **Залежності:** для рекомендованого A — .03b/.03c/.04c/.05b/.07a/.07b/.07c/.08a та D1/D6/D7. `.08b` потрібна лише при keyless-producer рішенні; shared-credential topology може явно позначити її not applicable зі збереженням чинних auth/key tests. `.08c` потрібна для дозволеного paid diagnostic workflow; якщо його заборонено, ця картка натомість має реалізувати й перевірити explicit denial усіх probe paths. Непризначена картка не означає дозволений bypass. При виборі B/C переглянути applicability .08d, не виконувати queue-default автоматично.
- **Acceptance:** усі entrypoints інвентаризовані й перевірені; жоден paid exception не обходить admission; default flags не вмикають paid generation; public GET лишається read-only. A01/A14.
- **Test strategy:** entrypoint matrix, scheduler producer-only/worker role, direct denied/allowed, migrations compatibility, no fallback on errors.
- **Ризики / розмір:** stranded queue, hidden caller, old binary bypass; **M**. Defaults switch лише після dependencies.

## STAB-015.09 — контрольований rollout і rollback runbook

- **Проблема:** source/config changes не доводять effective runtime state; старий binary може оминути нові ledger/fences.
- **Scope:** конкретний операторський runbook для one scheduler/one worker/PostgreSQL/public API, effective settings, readiness/freshness, stop-admission/drain/reconcile/rollback. Без broker або hard money budget за замовчуванням.
- **Залежності:** .08d, D7/D8; окрема operator authorization на кожен live rollout і paid activation.
- **Acceptance:** application, schema, role IDs, mapped env і sockets звіряються без credentials output; scheduler не запускається як тест; rollback зберігає ledger та не відновлює uncontrolled direct path.
- **Test strategy:** documentation/tabletop review і isolated config rendering; disposable fake-provider rehearsal уповноваженим інтегратором; live actions лише за окремим планом.
- **Ризики / розмір:** mixed versions, overlapping workers, source binds, stale environment, irrecoverable audit loss; **S** як runbook. Implementation/deployment не входять у цю документаційну картку.

## Послідовні checkpoints для малого deployment

1. **Без зміни execution architecture:** окремо призначити .03a, .05a, .07a і .07b.
   Результат — передбачуваний duplicate outcome та read-only видимість стану.
   Paid gate лишається denied; scheduler не відновлюється як перевірка.
2. **Рішення й invariants:** .01, потім потрібні .02/.03 та .04 leaf-картки за їх
   залежностями. Після кожної — safe regression suite; частково підключене fencing
   не дає дозволу на paid reclaim. Money budget і новий broker не входять за замовчуванням.
3. **Контрольоване recovery:** .05b, погоджені .06 та .07c; fake-provider crash
   rehearsal без зовнішніх calls. Базовий monitoring з checkpoint 1 вже доступний.
4. **Лише вибраний production шлях:** .08a і застосовні .08b/.08c, потім .08d та
   .09 за owner decisions. Необов'язкові topology cards мають явний N/A або tested
   disabled outcome. Live rollout і paid activation окремо погоджуються.

Немає залежності від prerender POC, Ollama, Redis/Celery або збільшення кількості
workers. Для приблизно 13 прогнозів на день one-worker PostgreSQL topology
достатня як початковий варіант; ці checkpoints закривають correctness gaps, а не
створюють вимогу одразу впровадити весь backlog.

Broker, token/money budget, historical-stub remediation і зміна zero-active-sign
policy залишаються окремими owner decisions; вони не є прихованими prerequisites
для самого вибору PostgreSQL queue-default.
