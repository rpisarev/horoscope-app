// Read-only acceptance against the built, authenticated Caddy + Flask + PostgreSQL demo.
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { after, before, test } from 'node:test'

const base = new URL(process.env.DEMO_BASE_URL || 'https://localhost:18439')
assert.ok(['localhost', '127.0.0.1', '[::1]'].includes(base.hostname), 'Use the local disposable demo')
assert.equal(base.protocol, 'https:')
assert.equal(base.href, base.origin + '/', 'Supply an origin without credentials, path, query or fragment')
assert.ok(process.env.DEMO_BROWSER_PASSWORD_FILE, 'Set DEMO_BROWSER_PASSWORD_FILE to the demo Basic Auth password file')
const password = (await readFile(process.env.DEMO_BROWSER_PASSWORD_FILE, 'utf8')).replace(/\r?\n$/, '')
assert.ok(password.length > 0)
const fixture = JSON.parse(await readFile(new URL('../../../backend/fixtures/demo-2026-11-22-v2.json', import.meta.url), 'utf8'))
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const locales = ['en', 'uk', 'ru']
const copy = {
  en: { home: 'Today’s horoscope', choose: 'Choose your sign.', aries: 'Aries', archive: 'Horoscope archive', missing: 'No forecast has been published for this date.', invalid: 'Day not found' },
  uk: { home: 'Гороскоп на сьогодні', choose: 'Оберіть свій знак.', aries: 'Овен', archive: 'Архів гороскопів', missing: 'Прогноз ще не опубліковано.', invalid: 'Такий день не знайдено' },
  ru: { home: 'Гороскоп на сегодня', choose: 'Выберите свой знак.', aries: 'Овен', archive: 'Архив гороскопов', missing: 'Прогноз ещё не опубликован', invalid: 'Такой день не найден' },
}
const archive = '/archive/aries/2026/11'
const russianOnlyDay = '2026-11-21'
const forecastPath = day => '/horoscope/aries/' + day
const localized = (path, lang) => path + (lang === 'en' ? '' : '?lang=' + lang)
const uiApiPaths = ['/api/forecast', '/api/years', '/api/archive/month', '/api/signs/meta']
let browser
let context
let today
const exceptions = []

async function getJson(path, params, status = 200) {
  const url = new URL(path, base)
  url.search = new URLSearchParams(params).toString()
  const response = await context.request.get(url.href, { maxRedirects: 0 })
  assert.equal(response.status(), status, url.pathname + url.search)
  return response.json()
}

before(async () => {
  browser = await chromium.launch({
    executablePath: process.env.CHROME_BIN || '/usr/bin/google-chrome',
    args: ['--no-sandbox', '--disable-background-networking'],
  })
  context = await browser.newContext({
    baseURL: base.origin,
    httpCredentials: { username: 'demo', password, origin: base.origin },
    ignoreHTTPSErrors: true, // Caddy's local disposable CA.
    serviceWorkers: 'block',
    viewport: { width: 320, height: 568 },
    reducedMotion: 'reduce',
  })
  await context.route('**/*', route => {
    const request = route.request()
    return new URL(request.url()).origin === base.origin && request.method() === 'GET'
      ? route.continue() : route.abort()
  })
  context.on('page', page => page.on('pageerror', error => exceptions.push(error.message)))
  const meta = await getJson('/api/meta')
  assert.equal(meta.timezone, 'Europe/Kyiv')
  today = meta.business_date
  assert.match(today, /^\d{4}-\d\d-\d\d$/)
})

after(async () => {
  await browser?.close()
  assert.deepEqual(exceptions, [], 'Unexpected browser exceptions')
})

test('all enabled signs expose each exact published text and its English source', async () => {
  for (const locale of locales) {
    const metadata = await getJson('/api/signs/meta', { locale })
    assert.equal(metadata.locale, locale)
    const keys = metadata.items.map(item => item.key).sort()
    assert.ok(keys.includes('aries'))
    for (const date of fixture.dates) {
      const day = await getJson('/api/archive/day', { date, locale })
      assert.equal(day.locale, locale)
      assert.deepEqual(day.forecasts.map(row => row.sign_key).sort(), keys)
      for (const row of day.forecasts) {
        const record = fixture.records.find(item => item.sign_key === row.sign_key && item.target_date === date)
        assert.ok(record)
        assert.equal(row.date, date)
        assert.equal(row.locale, locale)
        assert.equal(row.forecast_type, 'daily')
        assert.equal(row.status, 'published')
        assert.equal(row.text, record.texts[locale])
        assert.equal(row.forecast, row.text)
        assert.equal(row.source, 'demo-fixture')
        assert.deepEqual(row.payload.source_key, {
          sign_key: row.sign_key, target_date: date, forecast_type: fixture.forecast_type, locale: 'en',
        })
        assert.equal(row.payload.source_version, fixture.id)
        assert.equal(row.payload.content_role, locale === 'en' ? 'original' : 'translation')
        assert.equal(row.payload.source_text_sha256, createHash('sha256').update(record.texts.en, 'utf8').digest('hex'))
        assert.equal(row.payload.ai_generated, false)
      }
    }
    const absent = await getJson('/api/archive/day', { date: fixture.missing_date, locale })
    assert.deepEqual(absent.forecasts, [])
  }
})

async function assertLanguage(page, locale) {
  await page.locator('html[lang="' + locale + '"]').waitFor()
  const control = page.locator('#language-select')
  assert.equal(await control.inputValue(), locale)
  assert.deepEqual(await control.locator('option').evaluateAll(options => options.map(option => option.value)), locales)
}

async function assertForecast(page, day, locale) {
  await page.waitForURL(base.origin + localized(forecastPath(day), locale))
  await assertLanguage(page, locale)
  const json = await getJson('/api/forecast', { sign: 'aries', date: day, locale })
  assert.equal(json.locale, locale)
  if (day === russianOnlyDay) {
    assert.equal(json.payload.demo_dataset, 'demo-2026-11-15-v1')
    assert.equal(locale, 'ru')
  } else {
    const expected = fixture.records.find(record => record.sign_key === 'aries' && record.target_date === day)
    assert.equal(json.text, expected.texts[locale])
  }
  assert.ok((await page.locator('h1').innerText()).includes(copy[locale].aries))
  const paragraphs = json.text.split(/\r?\n/).filter(Boolean)
  await page.locator('article').getByText(paragraphs.at(-1), { exact: true }).waitFor()
  const body = page.locator('article h2 + div > p')
  assert.deepEqual(await body.allInnerTexts(), paragraphs, 'Every displayed paragraph must match the publication')
}

async function assertMissing(page, day, locale) {
  await page.waitForURL(base.origin + localized(forecastPath(day), locale))
  await assertLanguage(page, locale)
  await page.locator('article').getByText(copy[locale].missing, { exact: true }).waitFor()
  const error = await getJson('/api/forecast', { sign: 'aries', date: day, locale }, 404)
  assert.equal(error.error, 'forecast_not_published')
  const recovery = page.locator('article a')
  const scope = { sign: 'aries', locale, type: 'daily', year: day.slice(0, 4), month: day.slice(5, 7), include_latest: '1' }
  const result = await getJson('/api/archive/month', scope)
  assert.equal(result.latest_published_date, fixture.window_end)
  await recovery.waitFor()
  const dateLabel = recovery.locator('time')
  assert.equal(await dateLabel.getAttribute('datetime'), fixture.window_end)
  const dateText = new Intl.DateTimeFormat(locale, {
    year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC',
  }).format(new Date(fixture.window_end))
  assert.equal((await dateLabel.textContent()).replaceAll('\u00a0', ' '), dateText.replaceAll('\u00a0', ' '))
  assert.equal(await recovery.getAttribute('href'), localized(forecastPath(result.latest_published_date), locale))
  return recovery
}

async function assertFits(page) {
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 320, 'No horizontal overflow at 320px')
}

for (const locale of locales) {
  test(locale + ' at 320px: Home → Aries → archive → another published day → missing-day recovery', async () => {
    const page = await context.newPage()
    const reads = []
    page.on('request', request => {
      const url = new URL(request.url())
      if (uiApiPaths.includes(url.pathname)) reads.push(url)
    })
    try {
      await page.goto(localized('/', locale))
      await assertLanguage(page, locale)
      await page.getByRole('heading', { name: copy[locale].home, exact: true }).waitFor()
      await page.getByText(copy[locale].choose, { exact: true }).waitFor()
      const aries = page.getByRole('button', { name: copy[locale].aries, exact: true })
      const control = page.locator('#language-select')
      await control.focus()
      await page.keyboard.press('Tab')
      assert.ok(await aries.evaluate(el => el === document.activeElement), 'Tab reaches Aries from the language switcher')
      const controlBox = await control.boundingBox()
      const targetBox = await aries.boundingBox()
      assert.ok(controlBox && targetBox && controlBox.y + controlBox.height <= targetBox.y)
      await assertFits(page)
      assert.equal(await page.locator('.wheel-orbit').evaluate(el => getComputedStyle(el).animationName), 'none')
      const icon = await page.locator('link[rel=icon]').evaluate(el => el.href)
      assert.equal(new URL(icon).origin, base.origin)
      const response = await context.request.get(icon, { maxRedirects: 0 })
      assert.equal(response.status(), 200)
      assert.match(response.headers()['content-type'], /^image\/png/)
      assert.equal((await response.body()).subarray(0, 8).toString('hex'), '89504e470d0a1a0a')
      await page.keyboard.press(locale === 'uk' ? 'Space' : 'Enter')
      let firstDay = today
      if (!fixture.dates.includes(today)) {
        // Keep the real server date in use even after this fixture window closes.
        await (await assertMissing(page, today, locale)).click()
        firstDay = fixture.window_end
      }
      await assertForecast(page, firstDay, locale)
      await assertFits(page)
      const archiveLink = page.locator('nav a[href^="/archive/"]')
      assert.equal(await archiveLink.getAttribute('href'), localized(archive, locale))
      await archiveLink.click()
      await page.waitForURL(base.origin + localized(archive, locale))
      await page.getByRole('heading', { name: copy[locale].archive, exact: true }).waitFor()
      const calendar = page.locator('[aria-busy="false"]')
      const anotherDay = fixture.dates.find(day => day !== firstDay)
      const nextDay = calendar.locator('a[href="' + localized(forecastPath(anotherDay), locale) + '"]')
      await nextDay.waitFor()
      assert.equal(await calendar.locator('a[href*="' + fixture.missing_date + '"]').count(), 0)
      await assertFits(page)
      await nextDay.click()
      await assertForecast(page, anotherDay, locale)
      await page.reload()
      await assertForecast(page, anotherDay, locale)
      await page.goto(localized(forecastPath(fixture.missing_date), locale))
      await (await assertMissing(page, fixture.missing_date, locale)).click()
      await assertForecast(page, fixture.window_end, locale)
      await page.goBack()
      await assertMissing(page, fixture.missing_date, locale)
      await page.goForward()
      await assertForecast(page, fixture.window_end, locale)
      assert.deepEqual([...new Set(reads.map(url => url.pathname))].sort(), [...uiApiPaths].sort())
      assert.ok(reads.every(url => url.searchParams.get('locale') === locale), 'All localized UI reads carry the selected locale')
    } finally {
      await page.close()
    }
  })
}

test('switch language on a forecast and archive, reload, traverse history and normalize invalid lang', async () => {
  const page = await context.newPage()
  try {
    const day = fixture.window_start
    const control = page.locator('#language-select')
    await page.goto(forecastPath(day))
    await assertForecast(page, day, 'en')
    await control.focus()
    await page.keyboard.press('ArrowDown')
    await assertForecast(page, day, 'uk')
    await control.selectOption('ru')
    await assertForecast(page, day, 'ru')
    await page.reload()
    await assertForecast(page, day, 'ru')
    await page.goBack()
    await assertForecast(page, day, 'uk')
    await page.goForward()
    await assertForecast(page, day, 'ru')
    await page.locator('nav a[href^="/archive/"]').click()
    await control.selectOption('uk')
    await page.waitForURL(base.origin + localized(archive, 'uk'))
    await page.getByRole('heading', { name: copy.uk.archive, exact: true }).waitFor()
    await page.locator('[aria-busy="false"] a[href="' + localized(forecastPath(day), 'uk') + '"]').click()
    await assertForecast(page, day, 'uk')
    await control.selectOption('en')
    await assertForecast(page, day, 'en')
    await page.goto(forecastPath(day) + '?lang=invalid')
    await assertForecast(page, day, 'en')
    await page.goto(localized(forecastPath(fixture.missing_date), 'en'))
    await assertMissing(page, fixture.missing_date, 'en')
    await control.selectOption('uk')
    await (await assertMissing(page, fixture.missing_date, 'uk')).click()
    await assertForecast(page, fixture.window_end, 'uk')
    for (const locale of locales) {
      const invalid = localized('/horoscope/aries/2026-11-31', locale)
      await page.goto(invalid)
      await page.getByRole('heading', { name: copy[locale].invalid, exact: true }).waitFor()
      assert.equal(page.url(), base.origin + invalid)
      assert.equal(await page.locator('article').count(), 0)
    }
  } finally {
    await page.close()
  }
})

test('switch on Home, read the Russian-only V1 day and verify localized missing states and calendar links', async () => {
  const page = await context.newPage()
  try {
    const control = page.locator('#language-select')
    await page.goto('/')
    await page.getByRole('heading', { name: copy.en.home, exact: true }).waitFor()
    await control.selectOption('ru')
    await page.waitForURL(base.origin + localized('/', 'ru'))
    await assertLanguage(page, 'ru')
    await page.getByRole('heading', { name: copy.ru.home, exact: true }).waitFor()
    await page.getByRole('button', { name: 'Телец', exact: true }).waitFor()
    await page.goto(localized(archive, 'ru'))
    const dayLink = page.locator('[aria-busy="false"] a[href="' + localized(forecastPath(russianOnlyDay), 'ru') + '"]')
    await dayLink.click()
    await assertForecast(page, russianOnlyDay, 'ru')
    for (const locale of ['en', 'uk']) {
      await control.selectOption(locale)
      await assertMissing(page, russianOnlyDay, locale)
      const archiveLink = page.locator('nav a[href^="/archive/"]')
      await archiveLink.click()
      await page.waitForURL(base.origin + localized(archive, locale))
      const calendar = page.locator('[aria-busy="false"]')
      await calendar.locator('a[href="' + localized(forecastPath(fixture.window_start), locale) + '"]').waitFor()
      await calendar.getByText('21', { exact: true }).waitFor()
      assert.equal(await calendar.getByRole('link', { name: '21', exact: true }).count(), 0)
      // Returning to Russian on the same archive month restores the published day.
      await control.selectOption('ru')
      await dayLink.click()
      await assertForecast(page, russianOnlyDay, 'ru')
    }
    await page.goto('/archive/aries/2026/08')
    await page.getByRole('status').filter({ hasText: 'No forecasts have been published for Aries in August 2026.' }).waitFor()
    assert.equal(await page.locator('[aria-busy="false"] a').count(), 0)
    await page.goto('/horoscope/unknown/2026-11-23?lang=uk')
    await page.getByRole('heading', { name: 'Такий знак не знайдено', exact: true }).waitFor()
    assert.equal(page.url(), base.origin + '/horoscope/unknown/2026-11-23?lang=uk')
    assert.equal(await page.locator('article').count(), 0)
  } finally {
    await page.close()
  }
})
