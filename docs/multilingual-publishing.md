# Multilingual forecast publication

## D-LANG-01 · Accepted product direction

For each enabled sign, target date and forecast type, prepare one English original.
Validate that original before using it as the source for translation. Translate
Ukrainian directly from that exact English version. Translate Russian independently
from the same English version. Both translations should express the same forecast
in natural language for their readers.

Validate each translation for its requested language, fidelity to the source,
completeness and correct source reference. Each language has its own publication
state. Readers see a forecast only when their requested language has a published
row. For example, a published English original and a Ukrainian draft produce an
English forecast and a Ukrainian missing-day page. The recovery link looks up
the latest published day for the same sign, language and forecast type.

Sign and date identify the forecast for routing, variation, storage and audit.
The existing prompt constraint keeps them out of direct creative instructions.
The V2 examples illustrate the language flow. Permanent rules for tone, length,
structure and topics remain editorial decisions for a later iteration.

## Evidence in the private demo

The static V2 dataset covers 22–24 November 2026 in English, Ukrainian and
Russian. Each date has a text group for every enabled demo sign.
25 November exercises the missing-day experience in all three languages.
Each row uses the public forecast key of sign, domain date, locale and type.
The forecast text includes a localized demo label. [V2 dataset](../backend/fixtures/demo-2026-11-22-v2.json)

The importer places these source references in each published row's JSON payload.

| Field | Meaning in V2 |
| --- | --- |
| `source_key` | English source identity with `sign_key`, `target_date`, `locale=en` and `forecast_type=daily`. |
| `source_version` | The fixture dataset ID, `demo-2026-11-22-v2`. |
| `source_text_sha256` | SHA-256 of the exact UTF-8 English forecast, including its demo label and paragraph breaks. |
| `content_role` | `original` on English rows and `translation` on Ukrainian and Russian rows. |

The three rows in a group share the same source key, version and text hash.
The importer checks the English bytes against the stored hash. A reviewer can
then identify the precise original for each translation. Rows retain
`source=demo-fixture`, `provenance=static-demo-fixture` and `ai_generated=false`.
The importer records the actual publication timestamp and creates zero generation
jobs, attempts or token-usage records. [Fixture importer and runbook](demo-fixtures.md)

Public links use English when `lang` is absent. Ukrainian uses `?lang=uk` and
Russian uses `?lang=ru`. The frontend normalizes unsupported values to English
and sends an explicit `locale` on forecast, calendar, latest-date, year and
localized sign-metadata reads. The legacy backend API still defaults to Russian
when called directly without a locale. For English or Ukrainian sign metadata
missing its requested name, the response preserves its historical `name` and
sets `name_locale=ru`. The client can then use the bundled sign label in the
requested language. The independent `/api/meta` supplies the business date.

## Production work still open

Regenerating the English source raises decisions about version identity, which
translations need another review, and when readers move between versions.
Retry, invalidation, replacement and rollback semantics for that workflow
remain open. The V2 source version identifies a static dataset. It establishes
no production versioning or automatic translation machinery.

If a later implementation uses paid providers, an English generation request
and each translation request must participate in the applicable STAB-015
execution, admission and per-UTC-day paid HTTP-attempt accounting. Retries can
consume additional attempts. Three published languages alone cannot establish
request count, token use or cost. This decision authorizes no provider calls,
paid budget, scheduler change or production rollout. [Accepted execution ADR](adr/STAB-015-generation-execution.md)

## Repeat the browser acceptance check

Start the disposable local HTTPS demo with V1 and V2 imported, using the demo runbook.
Provide its loopback origin, a private file containing the `demo` user's Basic
Auth password, and an installed Playwright module. Run from the repository
root with the system Chrome executable, or set `CHROME_BIN`. [Demo stack](demo-stack.md)

```sh
DEMO_BASE_URL=https://localhost:18439 \
DEMO_BROWSER_PASSWORD_FILE=/path/to/private/demo-browser-password \
PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs \
node --test frontend/tests/browser/multilingualDemo.browser.mjs
```

The browser exercises the built SPA at 320 pixels, the native language selector,
keyboard sign selection, reduced motion, the dated archive, missing-day recovery,
refresh and history. It compares each displayed paragraph with Flask's response
and checks all enabled signs against the fixture's exact texts and English
source references. On 21 November, V1 supplies a Russian publication. The check
opens it, switches to English and Ukrainian, and confirms both the localized
missing state and the disabled day in their calendars. Home follows the real
`/api/meta` date. After the fixture
window, the check follows the localized recovery link to the last fixture date.
The disposable demo's TLS certificate is accepted for this local check.
