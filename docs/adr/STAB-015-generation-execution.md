# ADR STAB-015: основний шлях виконання генерації

## 1. Назва, статус і дата

**Назва:** Черга PostgreSQL як типовий шлях генерації; обмежене пряме виконання.

**Статус: Accepted — 2026-11-14.** Власник явно затвердив D1–D8 інструкцією
«STAB-015.01 — Accept Generation Execution Architecture ADR»; задана власником
дата рішення — 2026-11-14, документальне оформлення — 2026-11-15.
Це єдине нормативне джерело прийнятої execution policy. **Accepted не означає
Implemented або Deployed**: STAB-015.01 завершує лише decision contract, не дозволяє
paid generation, runtime restart, migrations, credential migration або deployment.
Backlog і handoff конкретизують реалізацію, але не змінюють D1–D8.

**Дата:** 2026-11-14, Europe/Kyiv.
**Власник рішення:** власник проєкту.

Основна джерельна база — локальний commit
`0b4cc05698a957b13411d149668208758367b6c2` — перевірений local і remote
`feature/main-page-start` після PR #22. Його tree збігається з попереднім
stabilization checkpoint `c191ea7`; STAB-007, STAB-001 та SAFE-001 уже інтегровані.

STAB-004 інтегровано в commit `900b4c2de2ff383ce6ffe30c948d827013c7a92e`:
виправлення CLI та retry-cap враховано як реалізовані, не як відкритий backlog.
На цьому інтегрованому коді пройшли **397 backend tests**.
Це окрема інтеграційна перевірка, не запуск у межах ADR і не доказ deployment.
У розділі 14 source references прив'язані до зазначених ревізій.

**Checkpoint прийняття:** `2b716598ec078cafe2146c2e4d66f1ec139dfab0`, PR #23,
перевірений local і remote `feature/main-page-start`. Його tree ідентичний
`12495a8`: містить STAB-002, STAB-004 і початковий STAB-015 поверх попередніх
safety fixes. Історичні source facts збережено; 397 tests не перезапускалися
в documentation-only STAB-015.01.

**Implementation delta — iteration 3, 2026-11-15:** На base `4fe11be` (PR #24)
реалізовано STAB-015.03a exact-key conflict normalization, .05a read-only per-job
inspection, .07a DB readiness та .07b coverage/queue visibility; окремо STAB-003
оновлює frontend toolchain. [CURRENT_STATE](../CURRENT_STATE.md) і
[backlog](STAB-015-backlog.md) містять поточні статуси та verification.
Source references і таблиці «поточна поведінка» нижче фіксують зазначені історичні
ревізії; для змінених вузьких ділянок цей delta і linked implementation docs
уточнюють їх. D1–D8 не змінені. Ledger/admission, fencing/recovery, pause/retry
policy, async migration, worker-only credentials і queue-default rollout ще не
реалізовані; нові read-only reports не надають recovery або paid authority.

**Implementation delta — iteration 4, 2026-11-15:** Base `17fb256` (PR #25).
STAB-015.02a додає порожню additive ledger schema `0006_generation_ledger`;
[P3 storage design](../generation-ledger-schema.md) reviewed integrator-ом, але
runtime writers, hard cap, locking/fencing і recovery ще не реалізовані.
STAB-015.08c-A блокує production paid probe у main/helper; .08c-B bounded audited
dev diagnostics залишається OPEN, як і решта .08c. Окремо виконані STAB-029,
SEC-001 та STAB-005. [CURRENT_STATE](../CURRENT_STATE.md) містить інтегровану
verification. Таблиці source facts нижче зберігають історичні ревізії; цей delta
уточнює лише зазначені реалізовані ділянки. D1–D8, paid deny default і runtime
не змінені; schema implementation не є deployed ledger або paid authorization.

**Implementation delta — iteration 5, 2026-11-15:** Base `ea3c0ec` (PR #26).
`.02b` записує execution starts для development/test; `.03b` забезпечує atomic
package admission (0007); `.02c` додає transaction-owned intent/observation
primitives, але не final paid coordinator/cap; `.04a` додає справжній claim epoch
і explicit bounded nonproduction renewal (0008), timing default disabled.
Known paid paths безумовно blocked до завершення admission/safety chain.
Complete fencing, automatic recovery, provider pause, async/keyless topology і
production rollout не реалізовані.
[CURRENT_STATE](../CURRENT_STATE.md) містить integrated verification;
[backlog](STAB-015-backlog.md) — точні completion/activation boundaries.
Історичні source facts нижче не переписані; D1–D8 не переглядаються.

## 2. Контекст і перевірені факти

### Межі доказів

Код, міграції та тести прочитано без імпорту application, DB-запитів чи provider
calls. Runtime scheduler **зупинений**, source bind mounts вказують на оригінальний
checkout, а live ports доступні на всіх інтерфейсах — це checkpoint, перевірений
інтеграційним аудитом до цієї роботи. Пізніша конфігураційна зміна не доводить, що live sockets
уже змінилися: runtime треба звіряти при окремому дозволеному застосуванні.

Оригінальний SAFE-000 report у призначеному worktree не знайдено. Повідомлення
про **3118 quota failures** і старий direct runtime є **user-reported historical
evidence**: тут не встановлено період, кількість HTTP requests, billing, первинну
причину чи точний зв'язок з job/run/attempt. Цифра не є вимірюванням поточного
коду. У baseline вже реалізовані STAB-007, STAB-001 та SAFE-001.

У старій entrypoint-таблиці `architecture.md` було «no universal paid-provider
opt-in», хоча SAFE-001 prelude й код уже містять глобальний guard. Це застарілий
рядок історичного baseline, а не відсутність guard у коді. Так само старий опис
CLI exit `0` не описує реалізований STAB-004. Для цих фактів цей ADR спирається на
source references E09/E24 та інтеграційний checkpoint, а не старі формулювання.

### Всі відомі шляхи входу

«Глобальний» тут означає guard у процесі, що виконує код, а не централізований
account switch. Enqueue authorization, execution admission і publication approval
є різними рішеннями. Посилання E/T розкрито в розділі 14.

| Шлях | Поточна поведінка та локальний дозвіл | Спільний guard / що не покривається |
| --- | --- | --- |
| Scheduler nightly, optional startup, retry-missing у direct mode | `GENERATION_SCHEDULER_USE_QUEUE=0` за замовчуванням; provider з `HOROSCOPE_PROVIDER`, default stub. Direct retry має time window і retry-run cap. Queue creation/worker opt-ins не застосовуються. | Lifecycle paid/publication preflight і adapter paid guard діють; queue count limits не діють. E01–E03, E09. |
| Scheduler queue producer | Scheduled/retry-missing jobs; coverage та active exact-key dedupe; OpenAI потребує `GENERATION_SCHEDULED_JOBS_ALLOW_OPENAI`. | Не виконує provider. Збережена згода на створення не є згодою на подальше виконання. E01, E04. |
| Scheduler polling worker | Окремий opt-in `GENERATION_JOB_WORKER_ENABLED`, `GENERATION_JOB_WORKER_ALLOW_OPENAI`; polling у тому самому scheduler process. | Worker/lifecycle/adapter guards і queue limits; увімкнений worker сам не вимикає direct scheduler. E01, E06–E09. |
| Admin immediate runs / retry-missing | Enabled API, bearer token; default provider stub; OpenAI потребує admin allow, request allow і API key. Синхронно повертає run envelope. | Спільний lifecycle, без queue counts. Retry endpoint окремо розрізняє missing/limit outcomes. E10. |
| Admin jobs / backfill / batch retry/cancel | Той самий auth; common queue parser теж викликає `_ensure_provider_is_allowed`, отже **API key потрібен навіть для enqueue OpenAI**. | Enqueue не виконує provider; execution повторно авторизується worker. Retry не є новим paid opt-in і зберігає provider. E10–E11. |
| Immediate package CLI | Default provider OpenAI; потрібні `--allow-openai` та key; explicit stub не успадковує OpenAI environment. | Lifecycle guards, без queue counts. STAB-004: лише actual run status `success` дає `0`, решта `1`. E12, E24. |
| Queue creation CLI | Default stub; OpenAI потребує `--allow-openai`; missing key лише попереджає; range/dry-run/coverage/dedupe. | Це відмінність від Admin queue producer; dry-run не є reservation. E05, E12. |
| Manual worker CLI | `--allow-openai` і key для дозволеного OpenAI; optional stale cleanup; явний batch limit. | Та сама queue service, count limits і guards. STAB-004: порожня batch або всі processed jobs success → `0`; будь-який інший job status → `1`. E06–E08, E12, E24. |
| Прямий виклик lifecycle / retry helper | Factory приймає explicit provider або environment/default stub; direct retry не успадковує provider попереднього run. | Paid/publication guards, але не queue counts; це внутрішній entrypoint, його не можна забути при обмеженні direct CLI/API. E02–E03, E09. |
| Низькорівневі claim / process-claimed helpers | Claim бере queued row; process-claimed перевіряє running і `locked_by` на вході. | `process_claimed_generation_job` перевіряє paid/publication/local worker gates, але count checks живуть у зовнішньому `process_generation_jobs`. E06–E08. |
| OpenAI adapter `generate` напряму | Literal canonical `openai` guard на вході та перед transport; mutable name не обходить його. | Не має queue admission, lifecycle audit або publication; SDK retries=0. E09, E13. |
| Standalone prompt probe | Власний SDK client, key, paid guard у main та `call_openai`; profile listing read-only. | Поза queue/lifecycle/publication; не вимикає SDK retries як adapter, не має його count/audit гарантій. E14. |
| Legacy stub helper, report, public reads | `generate_horoscope` явно stub і сам не persist; package report читає; public forecast GET читає тільки published. | Жоден public GET не повинен ставати producer або способом paid admission. E15, E20. |

### Облік: шість різних одиниць

| Одиниця | Що реально означає | Чого з неї не можна вивести |
| --- | --- | --- |
| Job | Намір/queue scope; `attempt_count` збільшується на claim, навіть якщо paid guard відмовить до run. | Provider attempt, HTTP request, витрачені tokens або гроші. |
| Run | Lifecycle для date/locale/type; може повернутися вже існуючий running run, або failed preflight run без items. | Один новий execution на кожен caller; успішну coverage лише з факту існування run. |
| Item | Один sign у run; published content пропускається; список зазвичай береться з enabled metadata. | Один HTTP request: item може бути skipped, preflight не створить items, retry дає декілька attempts. |
| Attempt | Lifecycle спроба з request/response/error payload; default до трьох на item. | Незмінний durable ledger усіх зовнішніх запитів: row лише flush перед provider, commit після item. |
| HTTP request | STAB-001 adapter робить не більше одного SDK request на виклик; локальна відмова може дати нуль. | Достовірну billing подію або відсутність remote completion при timeout. Probe має іншу SDK retry політику. |
| Tokens / money | Успішний adapter response може зберегти provider usage у JSON response payload. | Нормалізований повний ledger, reservation або жорстку грошову стелю: schema не має такого accounting. |

Наприклад, один job із N missing signs та A lifecycle attempts може спричинити
до N×A adapter requests за один повний run без crash, якщо кожна спроба доходить
до transport. N береться з фактичного scope, а не фіксованих 13. Це умовна межа
одного виконання, не межа майбутніх retries/reclaims, probe або account billing.
Output token limit не обмежує сумарно input tokens, кількість запусків чи вартість.

STAB-001 уже вимикає SDK retries у створених та injected real clients adapter.
Structured `insufficient_quota` дає одну failed attempt **на оброблений item**;
інші items і наступні runs можуть знову звернутися до provider. Transient 429,
timeouts/connection errors та validation retries залишаються у lifecycle; backoff
і cross-run circuit breaker не реалізовані. Не слід повторно ставити STAB-001
як нову задачу. E02, E13, T01–T03.

### Admission і атомарність baseline

Queue service defaults: backfill до 7 processed dates, до 2 OpenAI jobs на виклик
worker, до 10 started jobs на UTC day. Scheduler total batch default окремо дорівнює
1. `MAX_RETRY_RUNS_PER_DAY` фактично передається в count усіх retry runs для
**target date/locale/type**, без UTC-day фільтра; це не денний spend cap. E03, E05–E06.

Daily count використовує mutable `GenerationJob.started_at`, не історію starts.
Manual single/batch retry очищає `started_at`, `run_id`, error і timestamps, але
не скидає `attempt_count`. Отже сьогоднішній job зникає з daily count між retry та
новим claim; повторні claims одного job не накопичуються як окремі starts.
Stale requeue зберігає старий `started_at`, тому reclaim наступного UTC day може
взагалі не бути зарахований до нового дня. `max_job_attempts` перевіряє stale
recovery, а не звичайний claim/manual retry. Це source-verified семантика, не
виміряний runtime інцидент. E06–E08.

| Boundary | Наявний захист | Залишок / межа доказу |
| --- | --- | --- |
| Одна queued row → claim | PostgreSQL `FOR UPDATE SKIP LOCKED`, зміна status/owner/count і commit. | Захищає цей row при claim; не є lease fencing у provider/persistence. |
| Daily limit → claim | Count, потім окремий claim; per-call counter локальний. | Два workers можуть обидва бачити останній вільний slot і claim різні jobs. Guard не атомарний. |
| Active exact-key dedupe | Міграція 0005 має partial unique index для queued/running; model не дублює цей index. | SELECT-before-insert може програти race та отримати IntegrityError без нормалізації в idempotent duplicate response. DB не дозволяє два active exact keys, але caller recovery не завершений. |
| Dedupe scope | Hash включає job type, date, locale, type, provider, normalized signs. | Різні job types/providers, `signs=None` та explicit/subset lists можуть перекривати ті самі forecasts. |
| Run admission | SELECT running за date/locale/type перед INSERT. | Немає partial unique constraint/atomic reservation у migrations/model; два callers можуть пройти SELECT. Provider/sign subset не входять до lookup. |
| Retry-run cap | Count retry runs перед запуском. | Check/start race; manual/scheduled runs не витрачають цей retry-type cap. |
| Existing active run | Lifecycle повертає його caller. | Worker не чекає завершення: running відсутній у status map і стає failed job; це не доказ failure самого run. |
| Forecast persistence | Unique sign/date/locale/type, update-or-insert після provider. | Унікальна row не запобігає дубльованій зовнішній роботі; паралельний writer може overwrite або зіткнутися на INSERT. |
| Retry/cancel/stale actions | Перевірки status у Python; running single cancel заборонений, batch cancel лише queued. | Немає CAS/version predicate для status transitions; race з claim/completion лишається. |

Висновки про races отримано з порядку statements і schema, **не з проведених
concurrency experiments**. Наявні послідовні priority/owner/dedupe tests не доводять
відсутність міжпроцесних races. E02–E08, E16–E18, T04–T07.

## 3. Альтернативи

Історичне порівняння збережено для rationale. **D1 обирає A**, уточнену D2–D8:
production paid probe заборонений, shared scheduler/worker credential environment
не відповідає D7. Описані нижче можливі exceptions не є дозволом на них.

**A — queue-default / direct-restricted.** Schedule, backfill та звичайна ручна
генерація створюють PostgreSQL jobs; один worker виконує спільний lifecycle.
Direct залишається для local stub і явно дозволеної діагностики/відновлення.
Будь-який дозволений paid direct exception повинен пройти той самий admission і
облік, або бути заборонений до їх реалізації. Probe має окремо визначену політику.

**B — рівноправні direct і queue зі спільними guards.** Зберегти синхронні Admin/CLI
та queue як штатні інтерфейси; винести shared atomic admission, accounting і recovery
так, щоб direct не міг їх оминути. Lifecycle/validation/provider/persistence спільні,
але два orchestration contracts залишаються повноцінно підтримуваними.

**C — direct-only.** Schedule/Admin/CLI викликають lifecycle напряму; чергу перестати
використовувати після визначеного drain/retention. Зберегти runs/items/attempts,
додати shared admission та operational recovery там, де вони потрібні. Варіант
доречний для малої суто ручної системи з прийнятною втратою orchestration зручностей.

Жоден варіант сам по собі не забезпечує exactly-once remote requests або money cap.
Broker/Celery/Redis не є четвертим необхідним варіантом: перевірені проблеми
стосуються admission, transaction boundaries і ownership, а не відсутності broker.

## 4. Порівняльна матриця

Оцінки якісні для поточного масштабу й уже наявної PostgreSQL queue; це не benchmark.

| Критерій | A: queue-default / direct-restricted | B: рівноправні шляхи / shared guards | C: direct-only |
| --- | --- | --- | --- |
| Складність | Помірна: queue вже є; одна основна orchestration policy, але потрібні fencing/ledger та міграція callers. | Найбільша: одна core policy, два набори UX, timeout і recovery contracts. | Найменша поверхня запуску після міграції; необхідні locks/accounting можуть повернути значну частину складності. |
| Надійність | Durable intent до виконання; backlog переживає worker outage. Помилки lease/reclaim лишаються до fixes. | Direct не залежить від polling; натомість request/process lifetime й queue мають різні failure modes. | Мало рухомих частин; crash caller/scheduler вимагає зовнішнього способу повторити пропущений намір. |
| Audit | Зручно зв'язати intent → executions → run → attempts; потрібна immutable історія. | Можна досягти тієї ж повноти, якщо direct теж пише execution ledger; нині job відсутній. | Runs/items/attempts достатні для простого огляду; intent/claim/recovery історію треба додати окремо. |
| Cost control | Одне штатне місце admission; queue counts лише грубий proxy, не money budget. | Еквівалентний контроль можливий shared reservations для кожного шляху, дорожче довести non-bypass. | Можливий той самий контроль; вилучення queue не створює budget автоматично. |
| Recovery | Queued intent і batch tools корисні; uncertain remote outcomes потребують reconciliation. | Гнучкий manual recovery, але більше можливостей дублювання між direct і queued work. | Простий ручний повтор; складніший контроль missing dates, backfill та частково завершених packages. |
| Compatibility | Потрібен явний перехід synchronous callers на enqueue/status; local stub можна зберегти. | Найкраща початкова сумісність; ongoing test matrix більша. | Найбільша втрата чинних queue/batch APIs, worker tooling і delayed execution. |
| Migration | Поетапне обмеження direct після guards/visibility; старі jobs/runs зберігаються. | Менше змін API, більше shared-policy engineering і cross-path race tests. | Drain/retire queue, заміна batch/status/cancel workflows, план збереження історії. |

## 5. Прийнятий підхід і межі реалізації

Прийнято **queue-first A** для production: PostgreSQL queue, окремі credential
environments одного scheduler/producer і одного worker, keyless public/Admin API.
Redis/Celery/Kafka не потрібні. Поточний `tasks.py` поєднує producer і polling worker
в одному process; це **не** реалізація прийнятої D7 role isolation.

Enqueue не дає права витрачати кошти або publish. Worker перед **кожною** paid
provider request attempt, включно з дозволеним retry, проходить SAFE-001, локальні
permissions, provider/account pause, package ownership, UTC-day API-attempt
reservation і publication-policy preflight. Final adapter boundary не дозволяє
прямому caller обійти admission. Перед publication та всіма фінальними writes
повторно перевіряються epoch/ownership і publication policy. Public GET не є producer.

D2 вимагає immutable execution history і durable attempt intent. **Job, claim,
run, execution start і API-attempt reservation — різні одиниці.** Hard cap рахує
кожну admitted paid request attempt, а не jobs/runs; кожен retry резервується заново.
UTC day визначається admission timestamp, не target date або часом response.
Mutable `GenerationJob.started_at` та `attempt_count` не є таким ledger.

Мінімальна схема може містити execution/job/run/attempt links, canonical provider,
origin, admitted UTC timestamp, policy version та epoch, без загальної event-sourcing
системи. Outcomes можуть бути append-only events або контрольованими transitions,
які не переписують admission history. Потрібні additive migration, storage/retention
і reconciliation abandoned reservations; conservative overcount після crash —
свідомий компроміс, не доказ фактичного billing. Конкретний SQL ще не обрано.

Reservation і durable intent фіксуються атомарно до transport; SQL/структура
additive schema — implementation design. Не тримати DB lock протягом HTTP request.
Manual retry/reclaim/crash не стирає history і не обходить policy новим job ID.
Число cap ще не задане: це не unlimited default і не дозвіл paid activation.

Committed intent без outcome не доводить sent/not-sent. Crash до transport і після
remote acceptance може мати однаковий durable state: **unknown / requires_review**,
без automatic retry/refund. Automatic recovery лише за durable protocol evidence,
що paid transport не був досягнутий. Manual recovery — окрема authorization і audit.
Exactly-once external requests не обіцяється; локальний UUID/request ID не створює
provider-side idempotency. Відсутній response не є доказом відсутності витрат.

Heartbeat, epoch і fencing охоплюють publication, item/attempt, run/job finalization,
exception handlers та cleanup/retry/cancel writers. Частковий fencing не дозволяє
paid reclaim. Один worker не прибирає races із manual callers, deployment overlap
або старим owner після lease loss.

Reliable input/output usage збирається з provider metadata; monetary cost — лише
оцінка з provenance model/pricing/version. Missing usage позначається unknown, не
нулем або вигаданими tokens. **Hard monetary budget deferred**, але usage та
estimated-cost collection входять до прийнятого D2.

## 6. Прийняті рішення власника

Усі D1–D8 **Accepted** за явною інструкцією власника, дата рішення 2026-11-14; повторного погодження
цих choices не потрібно. Це target policy, не чинні implementation guarantees.
Runtime rollout, secrets migration і paid enablement — окремі авторизовані дії.

| ID | Прийнятий контракт | Чинний код на `2b71659` |
| --- | --- | --- |
| D1 | Queue-first A; PostgreSQL; один scheduler/producer і один worker. Regular production Admin/CLI enqueue → job ID → status/results. Paid direct disabled by default; local stub direct можна зберегти. Explicit compatibility/migration, без мовчазної заміни sync response. Redis/Celery/Kafka не потрібні. | Queue існує, але scheduler default direct, immediate Admin/package CLI синхронні; production routing/role restriction не реалізовані. |
| D2 | Hard **UTC-day paid API-attempt count cap**. Кожна admitted request attempt і дозволений retry мають immutable accounting, durable intent та atomic reservation до transport. History зберігається при retry/reclaim/crash; unknown не має automatic refund. Reliable input/output usage й estimated cost збираються без fabricated usage/billing. Hard money budget deferred; числовий cap pending configuration. | Mutable started-job counts та item attempts є; hard request-attempt cap, durable admission ledger і нормалізований usage/cost accounting відсутні. |
| D3 | Не більше одного active run на **date + locale + forecast_type**, незалежно від provider/job type/direct/queue/sign subsets. Concurrent caller отримує controlled busy/deferred без duplicate paid execution. Published forecasts зберігаються; retries normally missing-only. Sign-level parallelism deferred. | SELECT-before-INSERT не атомарний; exact-key job index не забезпечує package exclusivity. |
| D4 | Heartbeat, lease epoch і complete fencing; stale owner не publish/finalize. Published content зберігається. Automatic recovery лише з durable proof недосягнення paid transport. Ambiguous timeout/crash → `unknown / requires_review`; без automatic retry/refund. Manual recovery authorized/audited; exactly-once не обіцяється. TTL/heartbeat/deadlines — за вимірами. | Є початковий owner check та stale timestamps; heartbeat/final fencing/conservative protocol відсутні. Нові semantic outcomes ще не є ORM/API enum contract. |
| D5 | Limited safe transient retry, policy alternative B: structured `insufficient_quota` ставить provider/account-scoped pause; auth/permission failures, що потребують оператора, блокують automatic paid admission у відповідному scope. Resume лише authorized operator. Confirmed safely retryable rate-limit → **максимум одна додаткова application-level attempt**, bounded backoff і Retry-After у межах deadline. Unknown не повторюється. Connection failure retry лише з reliable proof, що transport не досягнуто. Text validation не запускає новий paid request за замовчуванням. Кожен retry проходить D2. Adapter SDK `max_retries=0` зберігається. | STAB-001 quota nonretryable і SDK retry ownership реалізовані. Lifecycle досі broadly retries 429/timeouts/connections/validation до 3 attempts; tightening D5 і cross-run pause відкриті. |
| D6 | Async production Admin/CLI зі status/results і explicit migration/deprecation sync clients. **Paid prompt probe заборонено в production**. Development diagnostics потребують explicit authorization, effective SAFE-001 і bounded auditable API-attempt accounting dev environment; без automatic publication. Production diagnostic exception не обходить queue admission. | Sync paths і probe існують; probe має SAFE-001, але не production ban, request ledger або прийняті retry guarantees. |
| D7 | **Лише production worker** має OpenAI credentials. Backend/Admin API та scheduler producer keyless. `STAB-015.08b` обов'язкова до цієї topology; enqueue authorization окрема від execution. SAFE-001/publication/local/admission checks усі потрібні. Shared scheduler/worker process не є ізоляцією. Secrets/runtime migration — окремо approved rollout. | Compose передає key backend і scheduler; admin enqueue parser вимагає key. Worker-only credential topology не реалізована. |
| D8 | Nightly model; повна published coverage current business day **до 06:00 Europe/Kyiv** за enabled-sign metadata, не fixed 13. Priority today → tomorrow → historical backfill з anti-starvation. Published content доступний при partial coverage; missing не фабрикуються, published не overwrite автоматично. Missing/partial після deadline → actionable failure. Liveness/DB readiness/worker progress/content freshness та quota/worker/deadline reasons розділені. Channel/retention/routing pending configuration. SLO не є paid authorization. | Є date/coverage helpers, priorities і public reads; deadline evaluation, fairness та повні operational signals не реалізовані. |

### 6.1. Невизначені параметри впровадження

Це не відкриття D1–D8 заново. До відповідного rollout конкретизувати:

| ID | Параметр | Уже прийнята межа |
| --- | --- | --- |
| P1 | Числовий daily cap, configuration validation, non-secret provider/account identity та mapping спільного admission scope. | UTC; кожна admitted paid request attempt враховується; жоден process/entrypoint не має обхідного private cap. |
| P2 | Measured heartbeat interval, lease TTL, request/overall deadlines, bounded backoff/jitter та Retry-After seconds/date handling. | Unknown не retry; safe rate-limit — максимум один додатковий attempt; SDK retries=0. |
| P3 | Atomic SQL/transaction protocol; representation unknown/requires_review; ownership/cancel transitions; release reservation для **доведено не відправленого** request. | Package scope, complete fencing, immutable history; unknown automatic refund заборонений. |
| P4 | Additive/versioned endpoint або explicit async flag, response fields, CLI migration/deprecation dates та status workflow. | Regular production async; жодної мовчазної заміни run envelope на job. |
| P5 | Конкретні authorized operators, manual recovery/resume workflow, audit/payload retention, alert recipients/channel/routing. | Permanent pause не self-resume; manual recovery audited; 06:00 SLO вже прийнято. |
| P6 | Nightly start time, evaluation interval, bounded fairness/aging weights і production locale/type scopes. | Today → tomorrow → backfill; жодної неявної зміни deadline/grace period; active metadata authoritative. |
| P7 | Reliable usage fields, pricing/model version source, валюта/точність оцінки; pinning model/prompt для дозволеного retry. | Missing usage unknown; estimate не actual billing; hard money budget deferred. |
| P8 | Deployment service/process layout, version compatibility, secrets migration, rollout/rollback owner. | One producer/one worker; key лише у worker; .08b та admission/recovery prerequisites обов'язкові. |

Нуль enabled signs має бути явним configuration/no-work випадком без static fallback
або fabricated coverage; точний SLO verdict для порожнього набору ще потребує
продуктового уточнення. Remediation historical published stubs і replacement policy
— окремі майбутні задачі; чинне accepted правило зберігає published data.

### 6.2. Прийнятий майбутній entry-point contract

**E:** admin enable/bearer/request/local producer permissions для enqueue без key.
**X:** worker-role key + SAFE-001 + local execution permission + D2 reservation на
кожну attempt + D3 ownership + D4 fencing + D5 pause/retry. **P:** validation,
production capability/allowlist за trusted execution identity та current epoch;
metadata не дає permission. **R:** automatic recovery лише proven pre-transport,
unknown → authorized operator review/audited action. Enqueue, X і P не замінюють
одне одного; runtime/paid activation погоджується окремо.

| Entry point | Enqueue authorization | Execution authorization | Publication authorization | Sync / async response | Paid permission | Recovery authority |
| --- | --- | --- | --- | --- | --- | --- |
| Nightly scheduler | Producer identity/local permission; scope/coverage validation | Лише worker X | Лише worker P | Async job IDs/status | Keyless; enqueue не paid request | Idempotent enqueue за policy; R лише worker/operator |
| Retry-missing scheduler | Producer permission, missing-only; не обходить pause/unknown/retry budget новим job | Worker X | Worker P | Async jobs або no-work/busy | No key/direct paid call | Не auto-requeue uncertain; R |
| Queue producer / creation CLI | E або authorized local producer; range/dedupe validation | Без transport | Не publish | Job/batch IDs, status окремо | Без provider key | Enqueue не recovery override; R |
| Queue worker | Authorized persisted jobs; claim не замінює права | X на кожну initial/retry attempt | P перед persistence | Async execution; protected status/audit | Worker-only key; cap/pause mandatory | R; stale owner не mutate/finalize |
| Immediate Admin API | Explicit async migration через E; sync contract не підмінюється | Regular production direct заборонений | API не publish | Явний job envelope; legacy rejection/deprecation за P4 | Keyless, no paid direct bypass | Окремий authorized/audited operator workflow |
| Admin jobs/backfill | E; .08b відділяє enqueue permission від key | Worker X; D8 priority | Worker P | Job/batch IDs + status/results | API keyless | Retry/cancel окремо; unknown не auto-retry |
| Generation package CLI | Explicit migrated producer invocation/local authorization | Production enqueue; local stub direct можна | Production P у worker; local stub policy збережена | Async job ID; explicit migration старого exit/report contract | Production CLI без OpenAI key | Read/status; authorized R |
| Manual worker CLI | Не створює bypass jobs | Authorized worker environment з X; не другий неконтрольований worker | P | Sync command/batch report | Worker-only key; --allow-openai не override | R; --close-stale не доказ safe paid replay |
| Direct lifecycle helpers | Не production producer API | Local stub або internal worker dispatch з X; standalone production paid direct denied by default | P і fencing при worker dispatch | Internal sync lifecycle, не public sync production contract | Без незалежного budget/key exception | R; legacy None/running не дозвіл повтору |
| OpenAI adapter | Немає | Valid admitted attempt context + final SAFE-001/X; SDK retries=0 | Сам не publish | Sync internal result/error | Не standalone production bypass | Evidence/outcome; сам не refund/retry unknown |
| Standalone prompt probe | Не production producer; development explicit diagnostic permission | Paid production main/helper forbidden; dev SAFE-001 + bounded auditable admission | Ніколи automatic publication | Dev diagnostic output; read-only listing збережено | Немає production exception/key; dev окремий bounded environment | Unknown не replay/refund; authorized dev operator |
| Public read APIs | Немає | Немає provider calls | Немає writes; published-only reads | Sync reads, чинні aliases/404 | Немає | Жодної mutation або hidden enqueue |

### 6.3. Відмінності чинного коду

Матриця розділу 2 та E01–E24 — source facts. Nightly/retry scheduler досі default
direct; optional worker у тому самому process. Immediate Admin/package CLI sync;
admin job parser потребує key. Worker рахує mutable jobs; adapter/probe не мають
durable per-request admission, probe не має production ban. Lifecycle max_attempts=3
та broadly retryable timeouts/connections/validation не відповідають D5. Немає atomic
package exclusivity, heartbeat/epoch/final fencing, request ledger, deadline SLO
або worker-only production credentials. Нові guarantees тут не реалізовано.

Public read contracts, STAB-001 SDK retries=0, SAFE-001 default deny і STAB-004 exits
уже реалізовані. SAFE-001 unset/invalid/0 залишається denied; Accepted не paid permission.

## 7. Наслідки

Користь прийнятого A — один основний execution policy, видимий backlog, можливість
керувати retry/recovery і пов'язувати намір з durable audit. Public reads не
залежать від availability provider; worker outage зберігає вже published content.

Витрати — asynchronous UX і статуси для колишніх immediate callers, schema/retention
для ledger, fencing усіх persistence boundaries, operational обов'язок обслуговувати
завислі й uncertain executions. Один worker може затримати today content через довгий
backfill; priority без fairness здатний голодувати backfill. Новий broker цього
автоматично не виправляє.

B зберігала б synchronous workflows ціною двох orchestration paths; C спрощувала б
запуск ціною queue/batch можливостей. Власник обрав A: B/C збережені як alternatives
considered, а не pending вибір.

## 8. Детальна матриця відмов

«Ризик» нижче — source-derived можливість, якщо не зазначено інше. Нові засоби
захисту в останній колонці — accepted target, який ще потрібно реалізувати. A-сценарії визначено в розділі 12.

| Відмова / interleaving | Поточний результат / межа | Прийнята цільова реакція і критерій |
| --- | --- | --- |
| Global paid gate denied до lifecycle/provider | Failed preflight run без items/attempts; worker denial після claim дає failed job без run, claim уже порахований. E02/E08/E09, T03. | Зберегти fail-closed й чесні denial/claim metrics; не називати це HTTP attempt. A01. |
| Gate вимкнено після preflight | Adapter recheck зупиняє transport; можлива одна honest failed lifecycle attempt; in-flight request не відкликається. | Зберегти SAFE-001; явно розрізняти local denial та remote unknown. A01/A08. |
| Daily last slot: два workers | Count-then-claim може перевищити count cap; SKIP LOCKED не блокує різні rows. | Atomic reservation і monotonic ledger; два contenders, один slot. A03. |
| Manual retry / stale reclaim переходить UTC midnight | Timestamp reset стирає старе daily membership; stale reclaim зберігає вчорашнє. | Новий immutable execution/start на кожен admission; boundary tests. A02. |
| Два producer INSERT одного dedupe key | Partial unique index не дає duplicate active rows; loser може отримати необроблений DB conflict. | Rollback власної transaction/savepoint і reload active job зі збереженням caller transaction ownership; bounded conflict normalization без ослаблення index. A04. |
| Перекривні subsets/providers/job types | Dedupe hashes різні; active-run SELECT не атомарний. | Реалізувати accepted D3 package exclusivity, reserve shared forecast scope. A04/A05. |
| Одночасний run admission / retry-cap check | Обидва можуть пройти SELECT/count до INSERT; existing running run іноді повертається caller. | Atomic scope admission, явний busy/no-work outcome; без нового provider call. A05. |
| Queue бачить already-running run | Running відсутній у worker final status map → failed job, run може ще працювати. | Не оголошувати чужу роботу finished; визначити wait/defer contract. STAB-004 CLI правильно сигналізує non-success, але race не вирішує. A05. |
| Stale lease, старий owner ще живий | Cleanup очищає owner; новий owner може claim, старий не перевіряє epoch перед save/final writes. | Heartbeat + epoch + CAS у всіх writes; stale owner не publish/finalize. A06. |
| Run > stale threshold, але прогресує | Run cleanup використовує started_at (default 2h), job cleanup locked_at (default 60m), без heartbeat; можуть розійтися. | Розділити overall duration і lease health; bounded renew та reconciliation job/run. A06. |
| Crash після claim, до run/provider | Durable running job/count, provider міг не викликатися; stale policy requeue/fail. | Лише durable phase + protocol invariant, який виключає transport, дозволяє pre-transport classification. Інакше unknown навіть за наявності execution intent. A07. |
| Crash після flush attempt, до provider | Attempt ще не committed; rollback може прибрати його, pending item уже committed. | Durable attempt intent зберігає намір, але не доводить send/no-send; відсутність result не дозволяє automatic refund/retry. A07. |
| Timeout / crash після provider, до audit/forecast commit | Remote completion/charge можливі, durable attempt може бути відсутній; retry може дублювати request. | Uncertain outcome, request identity, reconciliation/manual choice. Exactly-once не заявляти. A08. |
| DB commit помилка після provider | Item transaction rollback може втратити attempts/result; зовнішня дія не відкочується. | Durable intent з попередньої transaction; outcome unknown; не refund автоматично. A08. |
| Crash після item/forecast commit, до run/job final commit | Published result є, run/job можуть лишитися running; `run_id` job задається після lifecycle. | Reconcile через immutable execution/run linkage; published skip зберегти, статус відновити без provider. A09. |
| Retry або cancel паралельно з claim/finalize | Python status check не CAS; retry може конфліктувати з новим active exact key; single running cancel явно відхиляється. | Conditional transitions/version, DB conflict mapping; cancel не стверджує скасування in-flight HTTP. A10. |
| `insufficient_quota` | STAB-001: одна attempt на processed item, інші items/future runs лишаються можливими. | D5 provider/account pause; structured reason, authorized operator resume, без automatic cooldown-resume. A11. |
| Transient 429/timeout/validation failure | Lifecycle до max_attempts; adapter SDK retries=0; loop без backoff. | D5: safe rate-limit → максимум один додатковий attempt з Retry-After/deadline; unknown не retry; validation не запускає paid request за замовчуванням; connection потребує proof no transport. Кожен retry проходить D2. A11. |
| Retry cap досягнуто, forecasts missing | **Baseline bug:** lifecycle None помилково ставав success job. **STAB-004 fixed:** helper повторно читає missing; remaining missing → existing ProcessingError → failed job. Concurrent full coverage → None/success. E24. | Не дублювати fix у backlog. Зберегти regressions; recheck не дає транзакційної гарантії майбутньої coverage. A12. |
| Worker zero jobs через count limit | STAB-004 exit `0`; queue може лишитися непорожньою, missing content можливий. | Окремі blocked/backlog/freshness metrics; exit code не health/SLO. A12/A13. |
| API responds, DB unavailable або scheduler stopped | `/api/signs` static; baseline backend healthcheck його читає. Це не DB readiness і не свіжість content. E20/E22. | Окремі probes, no paid calls; freshness alerts independent від API liveness. A13. |

## 9. Зобов'язання сумісності

- Public `GET /api/forecast` лишається read-only/published-only; missing/unpublished
  → exact `404 forecast_not_published`. Existing published stubs лишаються readable
  та рахуються у skip/coverage, доки власник окремо не змінить data policy.
- `/api/signs` лишається array; forecast aliases `sign/sign_key`, `day/date`,
  `text/forecast`, `model_version/model_name` зберігаються. Archive availability
  залежить від published scope, не від job status або календарного положення.
- Product day — `APP_TIMEZONE` / `/api/meta`; domain dates `YYYY-MM-DD`; operational
  timestamps і daily accounting UTC. DST/UTC rollover тестуються окремо.
- Default enabled-sign selection query і archive active count не замінюються числом
  13. **Відома різниця baseline:** `get_enabled_sign_keys` при нуль enabled rows
  повертає static SIGNS, тоді як archive active count нуль. D8 вимагає metadata-
  authoritative coverage; точний zero-enabled SLO verdict ще не обрано. Цей docs
  changeset і STAB-004 не змінюють fallback у коді. E19–E20.
- Queue orchestration, lifecycle/audit, prompt construction/validation, provider і
  persistence лишаються окремими responsibilities. Sign/date — routing/variation/
  metadata, не creative prompt instructions. E21, T11.
- Production publication перевіряється за trusted execution identity/capabilities/
  allowlist, не returned source/model; stub local workflow збережено. Невірні result
  metadata залишаються окремою integrity problem, не способом дозволити publication.
- Job ID, batch ID, persisted provider, old run/attempt history і current serializers
  зберігаються. Provider повторного job не підмінюється; model/prompt зараз resolve
  під час execution і не повністю pinned на enqueue — будь-яку зміну погодити.
- STAB-004 exit contract уже виправлено: package only success `0`, worker empty/all
  success `0`, actual non-success `1`; argparse та existing validation semantics
  залишаються. Async migration не може назвати queued job «успішним forecast run».
- Admin immediate response `{run, requested}` не підміняється job envelope мовчки.
  Потрібні explicit async API/flag, migration window і статусний read path.
  Existing direct callers/test contracts підтримати або явно deprecate за D6.

## 10. Security та operations

SAFE-001 лишається process-wide fail-closed paid boundary; production publication
і локальні permissions незалежні. Зміна `.env` не змінює environment уже запущеного
process/container. Activation/recreation, scheduler start і paid permission — окремі
operational рішення; цей документ їх не виконує і не дозволяє.

**Key-only-worker прийнято D7, але ще не реалізовано.** Admin
`_parse_job_common_body` викликає `_ensure_provider_is_allowed`, який вимагає
`OPENAI_API_KEY`. Щоб producer/API працював без provider key, треба окремо розділити
enqueue authorization та execution credential checks, зберігши admin enable/token,
admin allow і request confirmation. Worker повторно перевіряє paid/local/key/
publication policy. Immediate paid Admin paths у keyless API треба disable або
явно migrate; paid probe у production заборонений D6, development diagnostics ізольовані.
Просте вилучення ключа з API зараз зламає OpenAI enqueue. E10.

Source baseline Compose використовує development serving, bind mounts і host ports;
configuration exposure змінюється окремим deployment workstream. Перед rollout перевірити effective
configuration без друку секретів: queue/direct roles, paid/publication flags, model,
target policy, limits, loopback/proxy boundaries, worker identity і actual sockets.
Baseline Compose не передає деякі supported limit/target-policy env settings;
їх наявність лише в root `.env` не доводить effective process value. E22.

| Сигнал | Прийнята цільова read-only семантика | Чого не означає |
| --- | --- | --- |
| Liveness | API/process відповідає. | DB usable, worker progress або content готовий. |
| Worker progress | Heartbeat, instance/epoch, last progress timestamp та bounded lease/deadline evidence. | Сам heartbeat не доводить provider success, quota availability або publication freshness. |
| DB readiness | Bounded SELECT і перевірка очікуваної schema revision; без migrations/writes/provider. | Scheduler живий, queue рухається, provider quota доступна. |
| Content freshness | Current business day: повна coverage enabled signs до 06:00 Europe/Kyiv. Після deadline missing/partial → actionable failure; published reads доступні. | Job/run success і full coverage опівдні не доводять, що SLO виконано о 06:00; historical deadline evidence може бути unknown. |
| Limits/quota/recovery | Queue depth/oldest age, admitted/denied, remaining reservation slots, reason blocked, retry exhaustion, stale leases, uncertain outcomes. | Job count не є money spend; provider quota не перевіряється платним health probe. |

Потрібні structured reason codes і кореляція job/execution/run/item/attempt/request,
без credentials, auth headers та raw prompt/response у звичайних metrics/logs.
Baseline attempts містять raw payload; Admin detail payload opt-in і bearer auth
не замінюють retention/redaction policy. Quota alerts мають відрізняти permanent
quota, transient throttling, local limit, missing key, disabled paid gate і publication
denial. Окремі alerts потрібні для missing/partial/stale content та paused worker.
No-work або all-skipped success не повинен приховувати stale content policy.

Усі майбутні DB-backed verification — серійно одним уповноваженим інтегратором через
`bash scripts/backend-test.sh` на disposable DB за [testing-safety.md](../testing-safety.md).
Mocks/MockTransport, жодних paid providers. STAB-007 не перевпроваджується.
Live DB writes, generation commands, migrations/restarts/volume operations не є
частиною STAB-015. Runtime rollout має власний операторський план з recovery,
без автоматичного fallback до необмеженого direct path.

## 11. Реалізація прийнятого рішення

**STAB-015.01 completed (documentation only); .03a/.05a/.07a/.07b completed
в iteration 3; .02a storage та .08c-A production probe ban completed в iteration 4.**
Решта карток, включно .08c-B, відкриті; production architecture не завершена.
[Backlog](STAB-015-backlog.md) містить stable IDs і prerequisite chain;
[iteration-3 handoff](STAB-015-next-iteration.md) зберігає ownership, початковий
scope та поточні completion markers. Призначення implementation task не є дозволом на live rollout.

1. **Виконано локально:** ранні незалежні changesets .03a dedupe, .05a per-job inspection, .07a DB
   readiness, .07b aggregate coverage/queue/SLO visibility; STAB-003 toolchain
   upgrade окремо. Вони не вводять новий ledger або runtime rollout.
2. .02a schema (completed, no writers) → .02b execution history → .02c durable request intent; .02d reliable
   usage/estimated cost. .03b package exclusivity; .03c UTC **API-attempt** cap
   з atomic reservation перед кожним transport. Job count не substitute.
3. .04a epochs/heartbeat → .04b publication/item/attempt fencing → .04c усі інші
   writers; лише потім .05b conservative recovery. Частковий fencing не deployable.
4. .06a quota/auth/permission pause та .06b limited safe retry з D2 admission;
   .07c execution diagnostics доповнює ранні read-only signals.
5. .08a explicit async compatibility → **обов'язкова .08b keyless migration**;
   .08c-A production probe ban completed; .08c-B bounded dev diagnostics pending; .08e окремі credential
   environments producer/worker. Вони більше не conditional N/A за D6/D7.
6. .08f today→tomorrow→backfill і fairness; .08d queue-default/direct restriction
   лише після ledger/admission/fencing/recovery/retry/visibility, compatibility,
   credentials/probe prerequisites. .09 — окремо approved rollout/secrets migration
   та paid enablement.

.02d, .06b, .08c і .08e мають явні commit boundaries у backlog, якщо не вміщуються
в один changeset. Перед schema constraints перевірити historical overlaps у
дозволеному середовищі без мовчазного видалення. Rollback не повертає binary,
який обходить ledger/fencing: спочатку stop admissions, контроль in-flight work,
збереження audit. Немає залежності від prerender/Ollama.

## 12. Сценарії приймання

Це **acceptance scenarios прийнятої, ще не реалізованої policy**, не вже виконані тести.
Existing tests у розділі 14 зберігаються як regressions. DB/concurrency/crash suites
виконує уповноважений інтегратор через harness; локальні fakes не доводять PostgreSQL locking.

| ID | Сценарій і вимірюваний результат |
| --- | --- |
| A01 | Кожен paid entrypoint при absent/invalid/0 gate не викликає transport; local opt-in не обходить його; denial before/after preflight має чесний audit. Stub development і production publication guard збережені. |
| A02 | Manual single/batch retry та stale reclaim того самого job до/після UTC midnight додають новий immutable start; попередні starts/links не стираються. Claim denial відрізняється від HTTP intent; refund policy тестується. |
| A03 | Дві sessions беруть останній UTC-day API-attempt slot: admitted лише одна request attempt. Retry потребує нового slot; job/run count не є одиницею cap. Manual retry/reclaim не стирає history; unknown не refund; rollover використовує admission UTC timestamp. |
| A04 | Одночасні exact-key enqueue дають одну active row й стабільну duplicate response; різні provider/job types/subsets перевіряються проти D3 scope invariant. Повтор retry із новим active duplicate не породжує 500. |
| A05 | Direct+queue і два retry callers одночасно перевіряють scope/cap: один admitted execution; loser не provider-call. Already-running run не трактується як завершена власна робота. |
| A06 | Старий worker зависає, lease expires, новий отримує epoch; старий повертається до save/finalize і не змінює forecast/audit ownership/job status. Heartbeat, finish/reaper race і повтор worker ID теж перевірені. |
| A07 | Fault injection після claim/execution/attempt-intent commit та безпосередньо до/після transport: однаковий durable intent без outcome класифікується unknown, без automatic refund/retry. Pre-transport classification допускається лише за незалежним durable phase/protocol доказом, що transport не міг бути досягнутий; сам intent таким доказом не є. |
| A08 | Fault injection після remote acceptance/timeout, до result commit і при DB commit failure: uncertain outcome збережений, автоматичний повтор/refund відповідає D4, exactly-once не стверджується. |
| A09 | Crash після published item commit і до run/job finalization: recovery зберігає published forecast, не робить новий provider call для нього й відновлює коректні links/counters. |
| A10 | Claim/cancel/retry/finalize у конкурентних sessions: лише дозволені conditional transitions; cancelled-before-claim не виконується; running cancellation не обіцяє скасувати remote request. |
| A11 | SDK retries=0 і structured quota permanent збережені. Quota/auth/permission pause блокує future applicable admission до authorized resume. Confirmed safe rate-limit: initial + максимум одна додаткова application attempt, Retry-After/deadline і нова D2 reservation. Ambiguous timeout/connection не retry; proof pre-transport окремо; validation не запускає paid request за замовчуванням. Старі lifecycle expectations про три transient attempts навмисно оновлюються під D5. |
| A12 | STAB-004 regressions: retry None + still missing → failed; concurrent complete coverage → no-work success; package non-success → 1; worker empty/all-success → 0, mixed → 1. Count-limit no-work не означає coverage/SLO success. |
| A13 | API alive + DB unavailable; API/DB ready + scheduler stopped; queue blocked; partial/missing/stale business-day content: кожен стан дає свій сигнал без provider calls, auto-generation або exposed secrets. |
| A14 | Keyless API/producer enqueue після .08b зберігає E permissions. Тільки worker має key і X. Production paid probe main/helper denied навіть при global=1; development explicit authorization і bounded auditable admission без publication. Legacy sync contract не підмінюється job envelope; public reads/aliases/prompt invariants збережені. |
| A15 | Reliable input/output usage і pricing/model provenance дають labeled estimated cost; missing usage unknown, не 0. Unknown remote outcomes не вигадують tokens/billing і не refund reservation. |
| A16 | Europe/Kyiv 05:59:59/06:00/після deadline, winter/summer UTC offsets та enabled-sign changes: missing/partial після deadline → failure з окремими quota/worker/deadline reasons. Published content readable. Priority today→tomorrow→backfill із bounded starvation; пізнє заповнення не є доказом виконання deadline. |

## 13. Що ще потребує конкретизації

D1–D8 не є відкритими питаннями. P1–P8 у §6.1 — numerical/configuration та
implementation details. Окремими уточненнями лишаються zero-enabled-sign SLO
verdict, model/prompt pinning, payload/ledger retention, notification routing і
конкретні операторські повноваження. Paid rollout та secrets migration не дозволені.

Не відкладаються: hard API-attempt cap (відкладено лише число), usage/estimated
cost collection, worker-only credentials, production probe ban, package scope і
06:00 Europe/Kyiv SLO. Deferred hard monetary budget, sign-level parallelism,
broker adoption і historical-stub remediation не є prerequisites наступних
незалежних fixes. Provider idempotency/retrieval дослідити перед використанням;
їх можливість не скасовує D4 unknown policy.

## 14. Точні джерела та межі перевірки

Первинні source facts з **baseline 0b4cc05** та STAB-004 `900b4c2` збережено.
Relative `file:function:line` references повторно звірено з **PR #23, 2b71659**;
T04/T05 coordinates оновлено після доданих STAB-004 tests без зміни висновків.
Для історичних E24/T13 прямо зазначено commit. Після нової інтеграції рядки можуть
зсунутися, тому ревізія та ім'я функції є частиною reference.
Тести прочитано як специфікацію поточної поведінки; інтеграційний запуск обліковується окремо.

| ID | Source references | Що підтверджує |
| --- | --- | --- |
| <a id="e01"></a>E01 | [backend/tasks.py:generate_daily_forecasts:335](../../backend/tasks.py#L335); [retry_missing_forecasts:479](../../backend/tasks.py#L479); [process_queued_generation_jobs:571](../../backend/tasks.py#L571); [nightly:612](../../backend/tasks.py#L612) | Direct/queue dispatch, local producer/worker gates, registered roles; startup branch 639–663. |
| <a id="e02"></a>E02 | [backend/app/services/generation_service.py:run_daily_generation:71](../../backend/app/services/generation_service.py#L71); [_process_generation_item:287](../../backend/app/services/generation_service.py#L287) | SELECT-before-INSERT run, preflight, item commit boundaries, attempt flush до provider, retries, publication. |
| <a id="e03"></a>E03 | [generation_service.py:run_retry_for_missing_forecasts:179](../../backend/app/services/generation_service.py#L179); [close_stale_running_runs:35](../../backend/app/services/generation_service.py#L35) | Target-date retry cap, None ambiguity, stale run без heartbeat. |
| <a id="e04"></a>E04 | [generation_job_service.py:create_scheduled_generation_job:660](../../backend/app/services/generation_job_service.py#L660); [create_scheduled_retry_missing_job:724](../../backend/app/services/generation_job_service.py#L724) | Producer coverage/duplicate/no-missing behavior. |
| <a id="e05"></a>E05 | [generation_job_service.py:build_generation_job_dedupe_key:287](../../backend/app/services/generation_job_service.py#L287); [create_generation_job:348](../../backend/app/services/generation_job_service.py#L348); [create_generation_jobs_for_range:472](../../backend/app/services/generation_job_service.py#L472); [_enforce_openai_backfill_range_limit:200](../../backend/app/services/generation_job_service.py#L200) | Exact-key fields, SELECT/INSERT, local creation opt-in, range bound і per-date commit. |
| <a id="e06"></a>E06 | [generation_job_service.py:count_openai_generation_jobs_started_today:230](../../backend/app/services/generation_job_service.py#L230); [process_generation_jobs:1170](../../backend/app/services/generation_job_service.py#L1170) | Mutable UTC timestamp count, per-invocation counter, check-before-claim. |
| <a id="e07"></a>E07 | [generation_job_service.py:claim_next_generation_job:1084](../../backend/app/services/generation_job_service.py#L1084); [close_stale_running_jobs:1123](../../backend/app/services/generation_job_service.py#L1123) | SKIP LOCKED, claim commit/count, stale requeue/fail та retained started_at. |
| <a id="e08"></a>E08 | [generation_job_service.py:process_claimed_generation_job:1265](../../backend/app/services/generation_job_service.py#L1265); [_ensure_provider_can_execute:1327](../../backend/app/services/generation_job_service.py#L1327); [_run_retry_missing_job:1365](../../backend/app/services/generation_job_service.py#L1365) | Entry owner check, final writes без epoch, guards, status mapping; остання функція має STAB-004 delta нижче. |
| <a id="e09"></a>E09 | [backend/paid_execution_policy.py:require_paid_execution:28](../../backend/paid_execution_policy.py#L28); [publication_policy.py:require_publication_provider:38](../../backend/app/providers/publication_policy.py#L38); [factory.py:get_horoscope_provider:9](../../backend/app/providers/factory.py#L9) | Exact process opt-in, publication identity/capabilities, provider defaults. |
| <a id="e10"></a>E10 | [generation_admin_service.py:_ensure_provider_is_allowed:230](../../backend/app/services/generation_admin_service.py#L230); [_parse_job_common_body:292](../../backend/app/services/generation_admin_service.py#L292); [create_manual_generation_run:372](../../backend/app/services/generation_admin_service.py#L372); [retry_missing_generation:407](../../backend/app/services/generation_admin_service.py#L407); [admin_auth.py:require_admin_api_access:25](../../backend/app/admin_auth.py#L25) | Admin auth/local permission, key requirement навіть enqueue; immediate run/retry contracts. |
| <a id="e11"></a>E11 | [generation_job_service.py:cancel_generation_job_batch:932](../../backend/app/services/generation_job_service.py#L932); [retry_failed_generation_job_batch:981](../../backend/app/services/generation_job_service.py#L981); [cancel_generation_job:1031](../../backend/app/services/generation_job_service.py#L1031); [retry_generation_job:1055](../../backend/app/services/generation_job_service.py#L1055) | Status checks, timestamp/link reset, retained attempt_count. |
| <a id="e12"></a>E12 | [generate_forecast_package.py:main:230](../../backend/utils/generate_forecast_package.py#L230); [create_generation_jobs.py:main:297](../../backend/utils/create_generation_jobs.py#L297); [warn_openai_key_missing:247](../../backend/utils/create_generation_jobs.py#L247); [process_generation_jobs.py:main:132](../../backend/utils/process_generation_jobs.py#L132) | CLI defaults/gates/calls; baseline exit semantics замінені E24. |
| <a id="e13"></a>E13 | [openai_provider.py:OpenAIHoroscopeProvider.__init__:49](../../backend/app/providers/openai_provider.py#L49); [generate:82](../../backend/app/providers/openai_provider.py#L82); [_get_client:151](../../backend/app/providers/openai_provider.py#L151); [_openai_error_code:357](../../backend/app/providers/openai_provider.py#L357); [_is_retryable_openai_error:378](../../backend/app/providers/openai_provider.py#L378) | SDK retries=0, literal paid guard, response payload, quota classification. |
| <a id="e14"></a>E14 | [openai_prompt_probe.py:call_openai:548](../../backend/utils/openai_prompt_probe.py#L548); [main:648](../../backend/utils/openai_prompt_probe.py#L648) | Standalone client/gates, profile-listing early return, відсутність lifecycle. |
| <a id="e15"></a>E15 | [forecast_service.py:generate_horoscope:42](../../backend/app/services/forecast_service.py#L42); [save_forecast:63](../../backend/app/services/forecast_service.py#L63); [forecast_package_report.py:main:518](../../backend/utils/forecast_package_report.py#L518) | Stub helper, update/insert publication guard, report path. |
| <a id="e16"></a>E16 | [backend/app/models.py:GenerationRun:177](../../backend/app/models.py#L177); [GenerationJob:215](../../backend/app/models.py#L215); [GenerationAttempt:398](../../backend/app/models.py#L398) | Схема accounting, mutable job link/timestamps, attempt uniqueness; немає execution ledger/fencing columns. |
| <a id="e17"></a>E17 | [0005_generation_jobs.py:upgrade:28](../../backend/migrations/versions/0005_generation_jobs.py#L28), [partial unique index:180](../../backend/migrations/versions/0005_generation_jobs.py#L180) | Існуючий DB-level active exact-key dedupe, не лише model/SELECT. |
| <a id="e18"></a>E18 | [0001_initial_schema.py:upgrade:19](../../backend/migrations/versions/0001_initial_schema.py#L19), [run table:82](../../backend/migrations/versions/0001_initial_schema.py#L82); [0002_add_generation_attempts.py:upgrade:39](../../backend/migrations/versions/0002_add_generation_attempts.py#L39) | Forecast uniqueness, відсутність active-run scope uniqueness, attempts унікальні лише в item. |
| <a id="e19"></a>E19 | [sign_service.py:get_enabled_sign_keys:7](../../backend/app/services/sign_service.py#L7); [generation_service.py:get_missing_forecast_signs:240](../../backend/app/services/generation_service.py#L240) | Enabled query/static empty fallback та published coverage. |
| <a id="e20"></a>E20 | [routes.py:_active_sign_count:167](../../backend/app/routes.py#L167); [meta:255](../../backend/app/routes.py#L255); [forecast:265](../../backend/app/routes.py#L265); [signs:299](../../backend/app/routes.py#L299); [business_date.py:business_datetime:12](../../backend/app/business_date.py#L12) | API contracts, static signs health limitation, business date. |
| <a id="e21"></a>E21 | [prompt_service.py:build_rendered_prompt:150](../../backend/app/services/prompt_service.py#L150); [build_provider_request:204](../../backend/app/services/prompt_service.py#L204) | Prompt messages та sign/date metadata separation. |
| <a id="e22"></a>E22 | [docker-compose.yml:services.backend:23](../../docker-compose.yml#L23), [backend.healthcheck:73](../../docker-compose.yml#L73), [services.scheduler:86](../../docker-compose.yml#L86) | **Baseline** topology, healthcheck, mapped env; пізніша configuration не є доказом зміни live runtime. |
| <a id="e23"></a>E23 | [paid-execution.md](../paid-execution.md); [openai-retries.md](../openai-retries.md); [testing-safety.md](../testing-safety.md) | Реалізовані SAFE-001/STAB-001/STAB-007, operational і test safety boundaries. |
| <a id="e24"></a>E24 | **Commit 900b4c2**, `backend/app/services/generation_job_service.py:_run_retry_missing_job:1365` (нова перевірка 1391); `backend/utils/generate_forecast_package.py:main:230` (return 278); `backend/utils/process_generation_jobs.py:main:132` (return 177). | **STAB-004 implemented**: None+missing failure, CLI result codes; не open backlog. Перевірено інтегрований код. |

| Test evidence | Точний baseline reference | Межа |
| --- | --- | --- |
| T01 | [test_openai_provider.py:test_sdk_http_errors_make_one_request_per_provider_call:442](../../backend/tests/test_openai_provider.py#L442); [test_sdk_transport_failures_are_retryable_without_hidden_retries:500](../../backend/tests/test_openai_provider.py#L500) | Real SDK + MockTransport, не paid traffic; adapter/injected clients. |
| T02 | [test_generation_service.py:test_openai_quota_lifecycle_attempts_match_http_requests_without_publication:252](../../backend/tests/test_generation_service.py#L252) | Quota one attempt/item проти transient трьох; no publication. |
| T03 | [test_paid_execution_lifecycle.py:test_disabled_queue_consumes_claim_but_creates_no_run_or_provider_attempt:71](../../backend/tests/test_paid_execution_lifecycle.py#L71); [test_paid_execution_adapter.py:test_post_preflight_denial_records_one_honest_nonretryable_attempt:78](../../backend/tests/test_paid_execution_adapter.py#L78) | Denial accounting до/після preflight. |
| T04 | [test_generation_job_service.py:test_process_generation_jobs_leaves_openai_queued_when_daily_limit_is_reached:529](../../backend/tests/test_generation_job_service.py#L529); [test_process_generation_jobs_respects_openai_per_run_limit:575](../../backend/tests/test_generation_job_service.py#L575) | Sequential limits, не multi-session atomic admission. |
| T05 | [test_generation_job_service.py:test_create_generation_job_reuses_active_duplicate:58](../../backend/tests/test_generation_job_service.py#L58); [test_process_claimed_generation_job_requires_lock_owner:653](../../backend/tests/test_generation_job_service.py#L653) | Sequential duplicate і entry owner check; не final fencing/crash recovery. |
| T06 | [test_generation_service.py:test_retry_for_missing_forecasts_returns_none_when_retry_limit_reached:419](../../backend/tests/test_generation_service.py#L419); [test_close_stale_running_runs_marks_run_and_items_interrupted:497](../../backend/tests/test_generation_service.py#L497) | Lifecycle None/stale contracts; worker interpretation оновлено STAB-004. |
| T07 | [test_admin_generation_jobs_api.py:test_admin_can_cancel_generation_job_batch:335](../../backend/tests/test_admin_generation_jobs_api.py#L335); [test_admin_can_retry_failed_generation_job_batch:417](../../backend/tests/test_admin_generation_jobs_api.py#L417) | Batch transitions послідовно, не claim/cancel race proof. |
| T08 | [test_publication_policy.py:test_final_guard_uses_captured_adapter_identity_not_result_metadata:237](../../backend/tests/test_publication_policy.py#L237); [test_persistence_rechecks_policy_changed_during_generation:219](../../backend/tests/test_publication_policy.py#L219) | Trusted identity і final publication recheck. |
| T09 | [test_api_forecast.py:test_missing_forecast_is_read_only_even_on_repeated_requests:43](../../backend/tests/test_api_forecast.py#L43); [test_forecast_endpoint_returns_published_forecast_with_compatible_aliases:18](../../backend/tests/test_api_forecast.py#L18) | Public no-generation contract та aliases. |
| T10 | [test_api_archive.py:test_archive_month_counts_active_signs_dynamically_with_or_without_sign:284](../../backend/tests/test_api_archive.py#L284); [test_business_date.py:test_business_date_boundaries:22](../../backend/tests/test_business_date.py#L22) | Active metadata і timezone boundaries. |
| T11 | [test_prompt_service.py:test_build_provider_request_keeps_sign_and_date_only_as_metadata:101](../../backend/tests/test_prompt_service.py#L101); [test_build_rendered_prompt_does_not_expose_sign_or_date_in_messages:52](../../backend/tests/test_prompt_service.py#L52) | Prompt compatibility. |
| T12 | [test_generation_job_worker.py:test_generate_daily_forecasts_uses_queue_when_enabled:98](../../backend/tests/test_generation_job_worker.py#L98); [test_generate_daily_forecasts_legacy_mode_calls_generation_service:180](../../backend/tests/test_generation_job_worker.py#L180); [test_tasks_registers_queue_worker_only_when_enabled:353](../../backend/tests/test_generation_job_worker.py#L353) | Dispatch/registration, не live scheduler liveness. |
| T13 | **Commit 900b4c2**, `backend/tests/test_generation_job_service.py:test_retry_missing_job_distinguishes_no_run_from_no_work:387`; `backend/tests/test_generation_job_service.py:test_worker_retry_limit_requires_complete_coverage:419`; `backend/tests/test_generation_cli_exit_codes.py:test_package_exit_status:102`, `backend/tests/test_generation_cli_exit_codes.py:test_worker_exit_status:129`, `backend/tests/test_generation_cli_exit_codes.py:test_worker_count_limit_is_legitimate_no_work:148`. | Нові STAB-004 regressions прочитано з commit; точні function/line coordinates перевірено static AST аналізом. |

**Verification:** первинний ADR мав source/schema/test та STAB-004 diff/AST review.
STAB-015.01 повторно перевірив baseline tree equivalence, current source boundaries,
86 function/class coordinates через AST без app import, relative links, 14 sections,
D1–D8/P1–P8, 12 future entrypoints, 16 acceptance scenarios, збереження stable card
IDs і acyclic prerequisite graph. `git diff --check` перевіряє whitespace.
Документ не вносить implementation; backend/frontend tests чи migrations у цій
роботі не запускалися. DB-backed results належать історичному інтеграційному
checkpoint; admission/fencing/crash guarantees прийнято як target policy,
implementation та acceptance tests відкриті.
