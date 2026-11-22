// Use the isolated release frontend and external Chrome tooling from docs/mobile-wheel.md.
import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const base = new URL(process.env.WHEEL_BASE_URL || 'http://127.0.0.1:54104')
assert.equal(base.hostname, '127.0.0.1')
assert.notEqual(base.port, '5173')
const scene = '.cosmic-gate404__scene'
const horizon = '.cosmic-gate404__event-horizon'
const segment = '.cosmic-gate404__segment'
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

async function checkAssembledRing(page) {
  const ring = await page.locator(scene).evaluate((el, selector) => {
    const devices = Array.from(el.querySelectorAll(selector))
    const designs = devices.map(device => [device.getAttribute('class'), device.getAttribute('href'), device.innerHTML].join('|'))
    return {
      bounds: el.getBoundingClientRect().toJSON(),
      segments: devices.map(device => device.getBoundingClientRect().toJSON()),
      visible: devices.every(device => device.checkVisibility({ opacityProperty: true, visibilityProperty: true })),
      designCount: new Set(designs).size,
    }
  }, segment)
  assert.ok(ring.segments.length >= 80 && ring.segments.length <= 90, 'Expected 80–90 gate devices')
  assert.equal(ring.designCount, 1, 'Every position uses the same device')
  assert.ok(ring.visible, 'Every device is visible')
  for (const box of ring.segments) {
    assert.ok(box.width > 0 && box.height > 0)
    assert.ok(box.left >= ring.bounds.left && box.right <= ring.bounds.right &&
      box.top >= ring.bounds.top && box.bottom <= ring.bounds.bottom,
      JSON.stringify({ clippedSegment: box, scene: ring.bounds }))
  }
  const xs = ring.segments.map(box => box.x + box.width / 2)
  const ys = ring.segments.map(box => box.y + box.height / 2)
  const width = Math.max(...xs) - Math.min(...xs)
  const height = Math.max(...ys) - Math.min(...ys)
  assert.ok(Math.min(width, height) > .9 * Math.max(width, height), 'Ring should be near-circular')
  const x = Math.min(...xs) + width / 2
  const y = Math.min(...ys) + height / 2
  const radii = xs.map((cx, i) => Math.hypot(cx - x, ys[i] - y))
  assert.ok(Math.min(...radii) > .88 * Math.max(...radii), 'Every device sits on the rim')

  // Sample well inside the aperture, away from the rim lights and surrounding stars.
  const size = Math.floor(Math.min(width, height) * .45)
  return { x: Math.round(x - size / 2), y: Math.round(y - size / 2), width: size, height: size }
}

async function apertureBrightness(page, clip) {
  const png = await page.screenshot({ clip, scale: 'css' })
  return page.evaluate(async base64 => {
    const image = new Image()
    image.src = 'data:image/png;base64,' + base64
    await image.decode()
    const canvas = document.createElement('canvas')
    canvas.width = canvas.height = 1
    const ctx = canvas.getContext('2d')
    ctx.imageSmoothingQuality = 'high'
    ctx.drawImage(image, 0, 0, 1, 1)
    const [r, g, b] = ctx.getImageData(0, 0, 1, 1).data
    return .2126 * r + .7152 * g + .0722 * b
  }, png.toString('base64'))
}

for (const [width, height] of [[1440, 900], [320, 568]]) {
  test(`${width}×${height} shows the entire assembled ring under reduced motion`, async t => {
    const page = await openGate(t, unknown, { viewport: { width, height }, reducedMotion: 'reduce' })
    await checkAssembledRing(page)
  })
}

test('one uninterrupted visit starts assembled and keeps the lit horizon through 30 seconds', async t => {
  const page = await openGate(t, unknown, { reducedMotion: 'no-preference' })
  const start = await page.evaluate(() => performance.now())
  const original = await page.locator(horizon).elementHandle()
  assert.equal(await original.evaluate(el => Number(getComputedStyle(el).opacity)), 0, 'Aperture starts inactive')
  const clip = await checkAssembledRing(page)
  const dark = await apertureBrightness(page, clip)
  for (const seconds of [10, 11, 20, 30]) {
    await page.waitForFunction(deadline => performance.now() >= deadline, start + seconds * 1000)
    assert.ok(await original.evaluate(el => el.isConnected && Number(getComputedStyle(el).opacity) >= .95),
      `Original horizon should remain fully visible at ${seconds}s`)
    const lit = await apertureBrightness(page, clip)
    assert.ok(lit > dark + 24, `Aperture should stay lit at ${seconds}s (inactive ${dark}, observed ${lit})`)
  }
})

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
      const clip = await checkAssembledRing(page)
      assert.ok(await gate.locator(horizon).evaluate(el =>
        el.checkVisibility({ opacityProperty: true, visibilityProperty: true }) && Number(getComputedStyle(el).opacity) >= .95))
      const lit = await apertureBrightness(page, clip)
      assert.ok(lit > 45, `Reduced motion should show the lit surface immediately (observed ${lit})`)
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
