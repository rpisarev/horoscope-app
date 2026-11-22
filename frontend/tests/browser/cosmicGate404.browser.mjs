// Use the isolated release frontend and external Chrome tooling from docs/mobile-wheel.md.
import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const base = new URL(process.env.WHEEL_BASE_URL || 'http://127.0.0.1:54104')
assert.equal(base.hostname, '127.0.0.1')
assert.notEqual(base.port, '5173')
const scene = '.cosmic-gate404__scene'
const unknown = '/lost-orbit'
let browser

before(async () => {
  browser = await chromium.launch({
    executablePath: process.env.CHROME_BIN || '/usr/bin/google-chrome',
    args: ['--no-sandbox', '--disable-background-networking'],
  })
})
after(async () => { await browser?.close() })

async function openGate(t, path, options = {}) {
  const page = await browser.newPage(options)
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  t.after(async () => {
    await page.close()
    assert.deepEqual(errors, [], 'Uncaught errors during the 404 visit or recovery')
  })
  await page.route('**/*', route => {
    const url = new URL(route.request().url())
    if (url.origin !== base.origin) return route.abort()
    if (url.pathname === '/api/meta') {
      return route.fulfill({ json: { business_date: '2026-11-22', timezone: 'Europe/Kyiv' } })
    }
    if (url.pathname === '/api/years') return route.fulfill({ json: [2026] })
    if (url.pathname === '/api/signs/meta') {
      return route.fulfill({ json: { locale: url.searchParams.get('locale'), items: [] } })
    }
    if (url.pathname.startsWith('/api/')) return route.abort()
    return route.continue()
  })
  await page.goto(new URL(path, base).href)
  await page.locator(scene).waitFor()
  return page
}

for (const [path, heading] of [
  ['/horoscope/unknown/2026-11-22', 'Zodiac sign not found'],
  ['/horoscope/aries/2026-02-30', 'Day not found'],
  ['/archive/aries/2026/13?lang=uk', 'Такий місяць не знайдено'],
  ['/archive/aries/2026/02/30?lang=ru', 'Такой день не найден'],
]) {
  test(`contextual 404 preserves ${path}`, async t => {
    const page = await openGate(t, path)
    await page.getByRole('heading', { level: 1, name: heading, exact: true }).waitFor()
    assert.equal(page.url(), new URL(path, base).href)
    assert.equal(await page.locator(scene).getAttribute('aria-hidden'), 'true')
    if (new URL(page.url()).searchParams.get('lang') === 'ru') {
      const home = page.getByRole('link', { name: 'На главную' })
      assert.equal(await home.getAttribute('href'), '/?lang=ru')
      await home.click()
      await page.waitForURL(new URL('/?lang=ru', base).href)
      await page.getByRole('heading', { name: 'Гороскоп на сегодня' }).waitFor()
    }
  })
}

test('unknown path switches language and the keyboard Home action keeps it', async t => {
  const page = await openGate(t, unknown)
  await page.getByRole('heading', { name: 'Page lost among the stars' }).waitFor()
  const language = page.getByRole('combobox')
  await language.selectOption('uk')
  await page.waitForURL(new URL(unknown + '?lang=uk', base).href)
  await page.getByRole('heading', { name: 'Сторінка загубилася серед зірок' }).waitFor()
  await language.focus()
  await page.keyboard.press('Tab')
  const home = page.getByRole('link', { name: 'На головну' })
  assert.ok(await home.evaluate(el => el.matches(':focus-visible')))
  await page.keyboard.press('Enter')
  await page.waitForURL(new URL('/?lang=uk', base).href)
  await page.getByRole('heading', { name: 'Гороскоп на сьогодні' }).waitFor()
})

for (const [width, height] of [[320, 568], [568, 320]]) {
  test(`${width}×${height} fits the gate and copy and permits pointer recovery`, async t => {
    const page = await openGate(t, unknown, { viewport: { width, height } })
    await page.locator('.business-status').waitFor({ state: 'detached' })
    const home = page.getByRole('link', { name: 'Back to home' })
    const heading = page.getByRole('heading', { level: 1 })
    for (const item of [page.locator(scene), heading, home]) {
      const box = await item.boundingBox()
      assert.ok(box && box.width > 0 && box.x >= 0 && box.x + box.width <= width)
      if (width > height && (item === heading || item === home)) {
        assert.ok(box.y >= 0 && box.y + box.height <= height, 'Landscape recovery fits before scrolling')
      }
    }
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    // Playwright scrolls as needed and checks that the action receives the pointer.
    await home.click()
    await page.waitForURL(base.href)
    await page.getByRole('heading', { name: 'Today’s horoscope' }).waitFor()
  })
}

for (const [width, height] of [[1440, 900], [320, 568]]) {
  test(`${width}×${height} shows the entire assembled ring under reduced motion`, async t => {
    const page = await openGate(t, unknown, { viewport: { width, height }, reducedMotion: 'reduce' })
    const ring = await page.locator(scene).evaluate(scene => {
      const bounds = scene.getBoundingClientRect().toJSON()
      const segments = Array.from(scene.querySelectorAll('.cosmic-gate404__segment'),
        element => element.getBoundingClientRect().toJSON())
      return { bounds, segments }
    })
    assert.ok(ring.segments.length > 0)
    for (const segment of ring.segments) {
      assert.ok(segment.width > 0 && segment.height > 0)
      assert.ok(segment.left >= ring.bounds.left && segment.right <= ring.bounds.right &&
        segment.top >= ring.bounds.top && segment.bottom <= ring.bounds.bottom,
        JSON.stringify({ clippedSegment: segment, scene: ring.bounds }))
    }
  })
}

test('reduced motion shows the assembled gate on entry and follows live preference changes', async t => {
  const page = await openGate(t, unknown, { reducedMotion: 'reduce' })
  const gate = page.locator(scene)
  for (const preference of ['reduce', 'no-preference', 'reduce', 'no-preference']) {
    await page.emulateMedia({ reducedMotion: preference })
    const reduced = preference === 'reduce'
    await page.waitForFunction(({ scene, reduced }) => {
      const animations = document.querySelector(scene).getAnimations({ subtree: true })
      return reduced ? !animations.length : animations.some(animation => animation.playState === 'running')
    }, { scene, reduced })
    if (reduced) {
      for (const part of ['.cosmic-gate404__event-horizon', '.cosmic-gate404__segment']) {
        const visible = await gate.locator(part).evaluateAll(elements =>
          elements.length > 0 && elements.every(el => el.checkVisibility({ opacityProperty: true, visibilityProperty: true }))
        )
        assert.ok(visible, `Static gate must show ${part}`)
      }
    }
  }
  const animations = await gate.evaluateHandle(el => el.getAnimations({ subtree: true }))
  await page.getByRole('link', { name: 'Back to home' }).click()
  await page.waitForURL(base.href)
  await gate.waitFor({ state: 'detached' })
  assert.ok(await animations.evaluate(items => items.length > 0 && items.every(
    animation => animation.playState !== 'running' && !document.getAnimations().includes(animation)
  )))
})
