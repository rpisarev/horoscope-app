# ADR STAB-015: основний шлях виконання генерації

## 1. Назва, статус і дата

**Назва:** Черга PostgreSQL як типовий шлях генерації; обмежене пряме виконання.

**Статус: Proposed / Pending owner approval.** Рекомендація, критерії приймання
та backlog нижче не є прийнятим архітектурним рішенням або дозволом на запуск.

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

У старій entrypoint-таблиці `architecture.md` залишилося «no universal paid-provider
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

## 5. Рекомендація — лише пропозиція

Рекомендується **A**: використати вже наявну PostgreSQL queue як типовий шлях.
Це концентрує operational admission та зберігає durable наміри, не вимагаючи broker.
Рішення не прийняте; просте перемикання `GENERATION_SCHEDULER_USE_QUEUE` не закриває
описані races і не є достатньою реалізацією ADR.

Запропонована мінімальна topology: PostgreSQL, public/API process, **один scheduler
producer і один worker**. Спочатку producer і worker можуть лишатися двома ролями
існуючого scheduler process, якщо це свідомо прийнятий спільний failure domain.
Розділення на процеси можна зробити для ownership/credentials без нового broker.
Один worker зменшує конкуренцію, але не прибирає Admin/CLI producers, ручний worker,
direct exception, старий завислий process, deployment overlap чи cross-path race.
DB invariants потрібні незалежно від штатної кількості workers.

Пропонується спільний admission boundary: scope reservation + budget-unit
reservation + execution identity фіксуються короткою DB transaction **до** provider.
Для daily admission — serializable/locked counter row або еквівалентна атомарна
reservation у PostgreSQL, а не count-then-claim. Це ще не вибір конкретного SQL.
Не тримати transaction/row lock на весь network request; завершення має окремо
перевіряти fencing token та чинність дозволу на publication.

Потрібна immutable історія **execution starts**: окремий execution ID, job ID
(nullable для погодженого direct), origin, scope, canonical provider, UTC admitted
time, policy snapshot/version, claim epoch, зв'язки з run/attempt та reservation.
Retry створює новий execution, а не стирає історію попереднього. Старт виконання,
permission denial і намір HTTP request мають різні event types; їх не називати
всі «provider attempts». Точну одиницю cap затверджує власник (D2).

Ledger не мусить бути загальною event-sourcing системою. Мінімум — append-only starts
і durable attempt intent перед transport; outcomes можуть бути окремими подіями
або контрольованими переходами, що не змінюють історичний timestamp. Ціна: нова
міграція, додаткові commits/storage/retention і reconciliation abandoned reservations.
Reservation перед викликом може бути витрачена без HTTP через crash; це консервативне
overcount, краще за приховане undercount для admission, але політику refund треба
визначити. **Committed intent сам по собі не доводить, чи HTTP був відправлений.**
Crash безпосередньо перед і після transport може залишити однаковий DB state.
Pre-transport classification дозволена лише тоді, коли durable phase та protocol
invariants доводять, що transport ще не міг бути досягнутий. Інакше outcome unknown;
автоматичні refund або retry не випливають із відсутності response.

Пропонується lease epoch/fencing token для claim, bounded heartbeat та CAS на
renew/recovery/finalization. Fencing має охоплювати **forecast publication та
item/attempt/run/job writes**, а не лише фінальний job status. Часткове покриття
writers не дає права оголосити fencing безпечним або вмикати auto-reclaim.
Перевірка перед
provider зменшує ризик, але не скасовує request, який уже полетів до втрати lease.

Після невизначеного network outcome неможливо атомарно узгодити PostgreSQL commit
і зовнішній HTTP side effect без підтвердженої provider-side idempotency/retrieval
гарантії. **Exactly-once external requests не обіцяється.** Пропонується durable intent,
at-least-once recovery лише там, де повтор дозволений, і явно видимий uncertain
outcome для решти. Provider request IDs допомагають reconciliation, але самі не
доводять idempotency чи повернення коштів. Підтримку конкретного API треба перевірити
при implementation, не припускати її з локального UUID.

## 6. Явні рішення власника

Всі рядки **Pending**. Затвердження документа не повинно непомітно дозволяти paid
execution, runtime restart, схему витрат або зміну public contracts.

| ID | Рішення, яке потрібне | Запропонований напрям |
| --- | --- | --- |
| D1 | A/B/C; які direct callers залишаються штатними? | A; local stub direct зберегти; paid direct лише погоджений exception зі shared admission. |
| D2 | Що лімітуємо: admitted executions, HTTP intents, tokens, money; scope й UTC window; refund rules? | Спочатку immutable execution/attempt intent облік та атомарний count cap; money budget лише окрема обґрунтована робота. |
| D3 | Scope exclusivity: package date/locale/type чи sign-level; різні providers, subsets, job types? | Почати з package scope, узгодженого з чинним active-run lookup; явно прийняти меншу паралельність. |
| D4 | Lease TTL/heartbeat, uncertain outcome policy, права manual recovery/cancel? | Epoch fencing; невідомий paid outcome не повторювати автоматично без reconciliation; running cancellation кооперативна лише якщо окремо спроєктована. |
| D5 | Реакція на quota/auth failures між items/runs; cooldown і resume authority? | Cross-run provider pause для підтвердженої permanent quota/auth причини; bounded backoff для transient errors; resume під контролем оператора. |
| D6 | Як мігрувати immediate Admin/CLI та standalone probe? | Версіонований/явний enqueue contract; probe як explicit diagnostic exception або через shared admission. Не перетворювати run response на job мовчки. |
| D7 | Мінімальна topology, розміщення provider key, production exposure і rollout owner? | PostgreSQL + один scheduler + один worker + public API; key-only-worker лише після producer-auth migration. |
| D8 | Freshness SLO, backlog priority, alert recipient, retention і допустимий partial coverage? | Separate liveness/readiness/freshness; today/tomorrow вище backfill, але з контролем starvation. |

## 7. Наслідки

Очікувана користь A — один основний execution policy, видимий backlog, можливість
керувати retry/recovery і пов'язувати намір з durable audit. Public reads не
залежать від availability provider; worker outage зберігає вже published content.

Витрати — asynchronous UX і статуси для колишніх immediate callers, schema/retention
для ledger, fencing усіх persistence boundaries, operational обов'язок обслуговувати
завислі й uncertain executions. Один worker може затримати today content через довгий
backfill; priority без fairness здатний голодувати backfill. Новий broker цього
автоматично не виправляє.

Збереження двох штатних execution paths за B виправдане, якщо synchronous потреба
важливіша за ці витрати міграції; це чесна альтернатива, але потребує однаково
сильного admission на кожному шляху. Direct-only C можна прийняти, якщо власник
свідомо відмовляється від нинішніх queue/batch recovery можливостей.

## 8. Детальна матриця відмов

«Ризик» нижче — source-derived можливість, якщо не зазначено інше. Нові засоби
захисту в останній колонці є пропозиціями. A-сценарії визначено в розділі 12.

| Відмова / interleaving | Поточний результат / межа | Запропонована реакція і критерій |
| --- | --- | --- |
| Global paid gate denied до lifecycle/provider | Failed preflight run без items/attempts; worker denial після claim дає failed job без run, claim уже порахований. E02/E08/E09, T03. | Зберегти fail-closed й чесні denial/claim metrics; не називати це HTTP attempt. A01. |
| Gate вимкнено після preflight | Adapter recheck зупиняє transport; можлива одна honest failed lifecycle attempt; in-flight request не відкликається. | Зберегти SAFE-001; явно розрізняти local denial та remote unknown. A01/A08. |
| Daily last slot: два workers | Count-then-claim може перевищити count cap; SKIP LOCKED не блокує різні rows. | Atomic reservation і monotonic ledger; два contenders, один slot. A03. |
| Manual retry / stale reclaim переходить UTC midnight | Timestamp reset стирає старе daily membership; stale reclaim зберігає вчорашнє. | Новий immutable execution/start на кожен admission; boundary tests. A02. |
| Два producer INSERT одного dedupe key | Partial unique index не дає duplicate active rows; loser може отримати необроблений DB conflict. | Rollback/reload existing active job; idempotent відповідь без ослаблення index. A04. |
| Перекривні subsets/providers/job types | Dedupe hashes різні; active-run SELECT не атомарний. | Узгодити D3, reserve shared forecast scope. A04/A05. |
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
| `insufficient_quota` | STAB-001: одна attempt на processed item, інші items/future runs лишаються можливими. | Окремо погоджений cross-run pause; structured reason, scope/cooldown/resume. A11. |
| Transient 429/timeout/validation failure | Lifecycle до max_attempts; adapter SDK retries=0; loop без backoff. | Bounded backoff/jitter/deadline; зберегти attempt accounting, не множити SDK retries. A11. |
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
  повертає static SIGNS, тоді як archive active count нуль. Це окреме owner question,
  не прихована зміна в ADR або STAB-004. E19–E20.
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

**Key-only-worker є пропозицією, не поточною можливістю.** Admin
`_parse_job_common_body` викликає `_ensure_provider_is_allowed`, який вимагає
`OPENAI_API_KEY`. Щоб producer/API працював без provider key, треба окремо розділити
enqueue authorization та execution credential checks, зберігши admin enable/token,
admin allow і request confirmation. Worker повторно перевіряє paid/local/key/
publication policy. Immediate paid Admin paths у keyless API треба disable або
явно migrate; probe/direct exception потребує окремого контрольованого середовища.
Просте вилучення ключа з API зараз зламає OpenAI enqueue. E10.

Source baseline Compose використовує development serving, bind mounts і host ports;
configuration exposure змінюється окремим deployment workstream. Перед rollout перевірити effective
configuration без друку секретів: queue/direct roles, paid/publication flags, model,
target policy, limits, loopback/proxy boundaries, worker identity і actual sockets.
Baseline Compose не передає деякі supported limit/target-policy env settings;
їх наявність лише в root `.env` не доводить effective process value. E22.

| Сигнал | Запропонований read-only зміст | Чого не означає |
| --- | --- | --- |
| Liveness | Процес відповідає; scheduler/worker heartbeat має timestamp і instance ID. | DB usable, worker admission enabled або content готовий. |
| DB readiness | Bounded SELECT і перевірка очікуваної schema revision; без migrations/writes/provider. | Scheduler живий, queue рухається, provider quota доступна. |
| Content freshness | Для business dates/locale/type: expected active signs, published/missing, partial coverage, age і last completed run. | Сам факт run/job success не доводить поточну повноту всіх scopes. |
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

## 11. Малий план реалізації після owner approval

Пункти нижче — сімейства робіт; їхні окремі leaf-картки є reviewable changesets:
[STAB-015 backlog](STAB-015-backlog.md). Спочатку можна окремо призначити
existing-contract duplicate fix (.03a), read-only recovery inspection (.05a),
базові DB readiness (.07a) та coverage/queue visibility (.07b). Вони не потребують
нового ledger або вибору production execution architecture; їхні вузькі output
contracts погоджуються у відповідних задачах.

1. Зафіксувати D1–D8, scope invariant і сумісність STAB-004 (STAB-015.01).
2. Розділити ledger schema, execution-start wiring та durable attempt intents
   на STAB-015.02a/.02b/.02c; історичні starts не вигадувати з mutable timestamps.
3. Незалежно нормалізувати exact-key conflicts (.03a); після рішень власника
   окремо реалізувати scope exclusion (.03b) та atomic count reservations (.03c).
4. Окремо додати lease epochs (.04a), forecast/item fencing (.04b), решту final
   writes (.04c); потім recovery mutations (.05b). Без повного writer coverage не оголошувати
   fencing safe і не вмикати auto-reclaim paid uncertain work.
5. Окремі quota/backoff (.06a/.06b) та execution diagnostics (.07c) зміни
   зберігають STAB-001 retry ownership.
6. Caller contracts (.08a), producer/key boundaries (.08b), probe (.08c),
   routing/default switch (.08d) мають власні review/test boundaries.
   Keyless migration потрібна лише за D7; paid probe може бути явно заборонений
   замість повної diagnostic integration. N/A не дозволяє залишити paid bypass.
7. Оператор окремо застосовує configuration за .09. Paid activation має власне
   явне рішення, не автоматичний наслідок завершення ADR.

До schema constraints перевірити старі overlapping active runs/jobs у дозволеному
середовищі; конфлікти не видаляти мовчки. Rollback спочатку зупиняє new admissions,
зберігає audit/ledger і контролює in-flight work; повернення старого binary, який
не знає ledger/fencing, може відновити bypass і потребує окремого compatibility gate.

## 12. Сценарії приймання

Це **майбутні acceptance scenarios**, а не заяви про вже виконані тести.
Existing tests у розділі 14 зберігаються як regressions. DB/concurrency/crash suites
виконує уповноважений інтегратор через harness; локальні fakes не доводять PostgreSQL locking.

| ID | Сценарій і вимірюваний результат |
| --- | --- |
| A01 | Кожен paid entrypoint при absent/invalid/0 gate не викликає transport; local opt-in не обходить його; denial before/after preflight має чесний audit. Stub development і production publication guard збережені. |
| A02 | Manual single/batch retry та stale reclaim того самого job до/після UTC midnight додають новий immutable start; попередні starts/links не стираються. Claim denial відрізняється від HTTP intent; refund policy тестується. |
| A03 | Дві незалежні DB sessions одночасно беруть останній reservation slot: admitted лише один; denied/deferred не має HTTP; crash після reservation не створює прихований вільний slot. |
| A04 | Одночасні exact-key enqueue дають одну active row й стабільну duplicate response; різні provider/job types/subsets перевіряються проти D3 scope invariant. Повтор retry із новим active duplicate не породжує 500. |
| A05 | Direct+queue і два retry callers одночасно перевіряють scope/cap: один admitted execution; loser не provider-call. Already-running run не трактується як завершена власна робота. |
| A06 | Старий worker зависає, lease expires, новий отримує epoch; старий повертається до save/finalize і не змінює forecast/audit ownership/job status. Heartbeat, finish/reaper race і повтор worker ID теж перевірені. |
| A07 | Fault injection після claim/execution/attempt-intent commit та безпосередньо до/після transport: однаковий durable intent без outcome класифікується unknown, без automatic refund/retry. Pre-transport classification допускається лише за незалежним durable phase/protocol доказом, що transport не міг бути досягнутий; сам intent таким доказом не є. |
| A08 | Fault injection після remote acceptance/timeout, до result commit і при DB commit failure: uncertain outcome збережений, автоматичний повтор/refund відповідає D4, exactly-once не стверджується. |
| A09 | Crash після published item commit і до run/job finalization: recovery зберігає published forecast, не робить новий provider call для нього й відновлює коректні links/counters. |
| A10 | Claim/cancel/retry/finalize у конкурентних sessions: лише дозволені conditional transitions; cancelled-before-claim не виконується; running cancellation не обіцяє скасувати remote request. |
| A11 | Quota fake: чинні STAB-001 one-request-per-adapter-call та one-attempt-per-quota-item збережені; нова погоджена cross-run pause не запускає future paid requests; transient errors мають bounded policy і audited attempts. |
| A12 | STAB-004 regressions: retry None + still missing → failed; concurrent complete coverage → no-work success; package non-success → 1; worker empty/all-success → 0, mixed → 1. Count-limit no-work не означає coverage/SLO success. |
| A13 | API alive + DB unavailable; API/DB ready + scheduler stopped; queue blocked; partial/missing/stale business-day content: кожен стан дає свій сигнал без provider calls, auto-generation або exposed secrets. |
| A14 | Keyless API enqueue після погодженої migration працює з усіма producer auth gates; worker без key/paid/local permission відмовляє. Direct/probe обходи відсутні; public API/aliases/prompt/date/active-sign contracts не змінені. |

## 13. Відкриті питання

1. Який synchronous Admin/CLI workflow справді потрібний власнику, а який можна
   перенести на enqueue/status? Це визначає A проти B та D6 migration window.
2. Яка одиниця й scope admission потрібні для прийнятного ризику витрат? Hard money
   budget потребує pricing/version, input/output usage, unknown outcomes і account
   reconciliation; job counts цього не доводять.
3. Чи retry повинен використовувати старий model/prompt snapshot або поточний?
   Provider job уже pinned, model/prompt — ні. Яка retention для payload/ledger?
4. Який package/sign-level conflict policy для overlaps і manual rerun? Чи потрібна
   replacement policy для вже published content, включно зі старими stubs?
5. Чи empty enabled-sign set означає no work/error? Static fallback generation і
   zero-active archive semantics зараз різні; не змінювати це без окремого рішення.
6. Які TTL, heartbeat interval, deadline/backoff і допустима затримка content?
   Без виміряних runtime durations тут не встановлено довільні «безпечні» числа.
7. Чи provider підтримує потрібні idempotency/retrieval semantics для цього API?
   Як оператор встановлює outcome, якщо response/request ID не був committed?
8. Хто може resume quota-paused work, робити refund reservation і повтор uncertain
   execution? Як не перетворити ручний override на неаудитований bypass?
9. Чи production public API і Admin API лишаються одним process? Потреба keyless
   producers і мережеві межі потребують окремого deployment рішення.

## 14. Точні джерела та межі перевірки

Позначення `file:function:line` нижче — координати **baseline 0b4cc05**, якщо прямо
не вказано STAB-004 commit. Relative links відкривають source; після інтеграції
номери рядків можуть зсунутися, тому ревізія та ім'я функції є частиною reference.
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
| T04 | [test_generation_job_service.py:test_process_generation_jobs_leaves_openai_queued_when_daily_limit_is_reached:433](../../backend/tests/test_generation_job_service.py#L433); [test_process_generation_jobs_respects_openai_per_run_limit:479](../../backend/tests/test_generation_job_service.py#L479) | Sequential limits, не multi-session atomic admission. |
| T05 | [test_generation_job_service.py:test_create_generation_job_reuses_active_duplicate:54](../../backend/tests/test_generation_job_service.py#L54); [test_process_claimed_generation_job_requires_lock_owner:557](../../backend/tests/test_generation_job_service.py#L557) | Sequential duplicate і entry owner check; не final fencing/crash recovery. |
| T06 | [test_generation_service.py:test_retry_for_missing_forecasts_returns_none_when_retry_limit_reached:419](../../backend/tests/test_generation_service.py#L419); [test_close_stale_running_runs_marks_run_and_items_interrupted:497](../../backend/tests/test_generation_service.py#L497) | Lifecycle None/stale contracts; worker interpretation оновлено STAB-004. |
| T07 | [test_admin_generation_jobs_api.py:test_admin_can_cancel_generation_job_batch:335](../../backend/tests/test_admin_generation_jobs_api.py#L335); [test_admin_can_retry_failed_generation_job_batch:417](../../backend/tests/test_admin_generation_jobs_api.py#L417) | Batch transitions послідовно, не claim/cancel race proof. |
| T08 | [test_publication_policy.py:test_final_guard_uses_captured_adapter_identity_not_result_metadata:237](../../backend/tests/test_publication_policy.py#L237); [test_persistence_rechecks_policy_changed_during_generation:219](../../backend/tests/test_publication_policy.py#L219) | Trusted identity і final publication recheck. |
| T09 | [test_api_forecast.py:test_missing_forecast_is_read_only_even_on_repeated_requests:43](../../backend/tests/test_api_forecast.py#L43); [test_forecast_endpoint_returns_published_forecast_with_compatible_aliases:18](../../backend/tests/test_api_forecast.py#L18) | Public no-generation contract та aliases. |
| T10 | [test_api_archive.py:test_archive_month_counts_active_signs_dynamically_with_or_without_sign:284](../../backend/tests/test_api_archive.py#L284); [test_business_date.py:test_business_date_boundaries:22](../../backend/tests/test_business_date.py#L22) | Active metadata і timezone boundaries. |
| T11 | [test_prompt_service.py:test_build_provider_request_keeps_sign_and_date_only_as_metadata:101](../../backend/tests/test_prompt_service.py#L101); [test_build_rendered_prompt_does_not_expose_sign_or_date_in_messages:52](../../backend/tests/test_prompt_service.py#L52) | Prompt compatibility. |
| T12 | [test_generation_job_worker.py:test_generate_daily_forecasts_uses_queue_when_enabled:98](../../backend/tests/test_generation_job_worker.py#L98); [test_generate_daily_forecasts_legacy_mode_calls_generation_service:180](../../backend/tests/test_generation_job_worker.py#L180); [test_tasks_registers_queue_worker_only_when_enabled:353](../../backend/tests/test_generation_job_worker.py#L353) | Dispatch/registration, не live scheduler liveness. |
| T13 | **Commit 900b4c2**, `backend/tests/test_generation_job_service.py:test_retry_missing_job_distinguishes_no_run_from_no_work:387`; `backend/tests/test_generation_job_service.py:test_worker_retry_limit_requires_complete_coverage:419`; `backend/tests/test_generation_cli_exit_codes.py:test_package_exit_status:102`, `backend/tests/test_generation_cli_exit_codes.py:test_worker_exit_status:129`, `backend/tests/test_generation_cli_exit_codes.py:test_worker_count_limit_is_legitimate_no_work:148`. | Нові STAB-004 regressions прочитано з commit; точні function/line coordinates перевірено static AST аналізом. |

**Verification для цього ADR:** source/schema/test review; локальна baseline tree
equivalence; read-only STAB-004 diff review; static reference/link, 14-section,
backlog-field та whitespace checks. Перевірено relative links, source symbols
і поля leaf-карток; STAB-004 function coordinates додатково перевірено в Git object.
Документ не вносить implementation; backend tests чи migrations у цій роботі
не запускалися. DB-backed results належать окремому інтеграційному checkpoint;
майбутні admission/fencing/crash guarantees лишаються proposed acceptance work.
