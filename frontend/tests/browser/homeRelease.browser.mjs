// Run against a disposable release frontend using the external Playwright
// installation and loopback URL described in docs/mobile-wheel.md.
import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const base = new URL(process.env.WHEEL_BASE_URL || 'http://127.0.0.1:54104')
assert.equal(base.hostname, '127.0.0.1')
assert.notEqual(base.port, '5173')
let browser
let page

before(async () => {
  browser = await chromium.launch({
    executablePath: process.env.CHROME_BIN || '/usr/bin/google-chrome',
    args: ['--no-sandbox', '--disable-background-networking'],
  })
  page = await browser.newPage()
  await page.route('**/*', route => {
    const url = new URL(route.request().url())
    if (url.origin !== base.origin) return route.abort()
    if (url.pathname === '/api/meta') {
      return route.fulfill({ json: { business_date: '2026-11-15', timezone: 'Europe/Kyiv' } })
    }
    if (url.pathname.startsWith('/api/')) return route.abort()
    return route.continue()
  })
  await page.goto(base.href)
  await page.getByRole('heading', { level: 1, name: 'Гороскоп на сегодня' }).waitFor()
  await page.getByText('Выберите свой знак.', { exact: true }).waitFor()
})
after(async () => { await browser?.close() })

test('built page declares a local icon that the release server serves as PNG', async () => {
  const icon = await page.locator('link[rel=icon]').evaluate(el => el.href)
  assert.equal(new URL(icon).origin, base.origin)
  const response = await page.request.get(icon)
  assert.equal(response.status(), 200)
  assert.equal(response.headers()['content-type'], 'image/png')
  const png = await response.body()
  assert.equal(png.subarray(0, 8).toString('hex'), '89504e470d0a1a0a')
  assert.equal(png.readUInt32BE(16), 64)
  assert.equal(png.readUInt32BE(20), 64)
})

function clearOfIntro(box, intro, inset = 0) {
  return box.right + inset <= intro.left || box.left - inset >= intro.right ||
    box.bottom + inset <= intro.top || box.top - inset >= intro.bottom
}

for (const [width, height] of [[320, 568], [320, 320], [360, 430], [480, 360], [568, 320], [650, 540], [700, 500], [768, 768], [1440, 900]]) {
  test(`${width}×${height}: Home instructions stay visible and clear of the wheel`, async () => {
    await page.setViewportSize({ width, height })
    await page.evaluate(() => window.scrollTo(0, 0))
    const header = page.locator('main header')
    const intro = await header.evaluate(el => el.getBoundingClientRect().toJSON())
    assert.ok(intro.left >= 0 && intro.right <= width && intro.top >= 0 && intro.bottom <= height)
    const samples = await page.evaluate(() => {
      const orbit = document.querySelector('.wheel-orbit')
      const signs = [...orbit.querySelectorAll('.wheel-sign')]
      const animations = orbit.getAnimations({ subtree: true })
      animations.forEach(animation => animation.pause())
      const samples = []
      for (let time = 0; time < 120000; time += 5000) {
        animations.forEach(animation => { animation.currentTime = time })
        samples.push(signs.map(el => el.getBoundingClientRect().toJSON()))
      }
      animations.forEach(animation => { animation.currentTime = 0 })
      return samples
    })
    for (const targets of samples) {
      assert.ok(targets.length > 0)
      assert.ok(targets.every(box => clearOfIntro(box, intro, 2)), 'Allow for the sign focus ring')
    }
    const signs = page.locator('.wheel-sign')
    for (const sign of await signs.all()) {
      await sign.hover()
      const tooltip = page.locator('.wheel-tooltip-center:visible, .wheel-tooltip-orbit:visible')
      await page.waitForFunction(() => !document.querySelector('.tip-enter-active, .tip-leave-active'))
      const detail = await tooltip.evaluate(el => el.getBoundingClientRect().toJSON())
      // Hovering a sign can scroll a short, square viewport.
      assert.ok(clearOfIntro(detail, await header.evaluate(el => el.getBoundingClientRect().toJSON())))
    }
    await page.mouse.move(0, 0)
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), width)
  })
}
