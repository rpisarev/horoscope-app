# OpenAI retry ownership

The [OpenAI adapter](../backend/app/providers/openai_provider.py) uses the pinned
`openai==2.37.0` SDK. The [generation lifecycle](../backend/app/services/generation_service.py)
owns retries, with a default maximum of three attempts per item. Each call to the
adapter makes at most one SDK request; SDK retries are disabled so an audit attempt
does not hide additional quota or transport retries.

The adapter creates SDK clients with `max_retries=0`. When given a real `OpenAI`
instance, it uses `client.with_options(max_retries=0)` to obtain a copy with retries
disabled. This preserves the injected transport, base URL, timeout, and headers
without changing the caller's retry setting. The copy shares the supplied HTTP
transport; the adapter does not take over closing the caller's resources. Small
protocol-compatible fake clients still need only `responses.create`; they are used
unchanged and are responsible for their own behavior.

Error classification reads the SDK exception's nonempty string `.code` first,
then a flat `.body["code"]` or nested `.body["error"]["code"]`. The sole permanent
quota code currently recognized is the exact `insufficient_quota`. Message text,
the error `type`, malformed metadata, and unknown quota-looking codes do not extend
that allowlist. Another permanent code needs verified semantics and regression
coverage before inclusion.

| Failure | Lifecycle retryable? |
| --- | --- |
| Structured `insufficient_quota` | No |
| Other HTTP 429, including `rate_limit_exceeded` or a missing code | Yes |
| SDK connection error or timeout | Yes |
| Authentication, permission, or bad request | No |
| Other existing nonretryable SDK classes (404, 422) | No |
| Internal server errors; fallback HTTP 408, 409, 429, or 5xx | Yes |

An exhausted-quota response therefore records one failed attempt for each
processed item, marks those items failed, and produces no forecast. It does not
stop the entire run before other items, disable later scheduler invocations, or
add a cross-run circuit breaker. Transient failures can consume all three lifecycle
attempts; no new backoff or scheduler/queue retry policy is introduced here.

The adapter's network boundary remains the `responses.create` call in `generate`.
Execution authorization must be checked immediately before it. This retry change
does not implement the separate paid-execution policy or authorize real requests.

[Provider tests](../backend/tests/test_openai_provider.py) exercise real SDK
exceptions using `httpx.MockTransport`, including an injected client with default
SDK retries and HTTP retry-advice headers. They assert one request per adapter
call for quota, transient 429, 400/401/403/500, and transport failures, and preserve
successful structured output and fake-client compatibility. Structured metadata
tests cover flat/nested bodies and reject message-only quota inference.
SDK platform metadata is fixed in those tests so Python does not spawn `uname`;
the real SDK request/error path still runs through `MockTransport`, and the test
harness keeps its network and child-process prohibitions.
[Lifecycle tests](../backend/tests/test_generation_service.py) assert one attempt
per item for exhausted quota versus three for transient 429, with matching mock
HTTP counts and no forecast persistence.

Integration verification (2026-11-14): **47 focused tests passed** on the explicit
custom disposable target `horoscope_test_stab001`, then **286 full backend tests
passed** through the guarded workflow. The SDK installed in the test image was
`2.37.0`. Both test projects cleaned up successfully. Later paid-policy integration
must retain scoped opt-ins for fake OpenAI tests and rerun these regressions.
No raw pytest, development-database mutation or real provider request was used.

SAFE-001 integration subsequently passed **126 focused** and **315 full backend
tests**, including these quota/SDK regressions with scoped global paid opt-ins for
fake transport. Default-denial and publication-policy tests remain separate.
