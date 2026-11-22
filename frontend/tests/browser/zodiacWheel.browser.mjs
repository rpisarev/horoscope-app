// Optional real-layout regression; uses externally supplied Playwright tooling.
// No backend is contacted. Run instructions are in docs/mobile-wheel.md.
import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const base = new URL(process.env.WHEEL_BASE_URL || 'http://127.0.0.1:54104')
assert.equal(base.hostname, '127.0.0.1', 'Use an isolated loopback frontend')
assert.notEqual(base.port, '5173', 'Never target the live frontend')
let browser

before(async () => {
  browser = await chromium.launch({
    executablePath: process.env.CHROME_BIN || '/usr/bin/google-chrome',
    headless: true,
    args: ['--no-sandbox', '--disable-background-networking'],
  })
})
after(async () => { await browser?.close() })

async function openPage(viewport, options = {}) {
  const context = await browser.newContext({ viewport, ...options })
  await context.route('**/*', route => {
    const url = new URL(route.request().url())
    if (url.origin !== base.origin) return route.abort()
    if (url.pathname === '/api/signs/meta') return route.fulfill({ json: { locale: 'en', items: [] } })
    if (url.pathname === '/api/meta') {
      return route.fulfill({ json: { business_date: '2026-11-15', timezone: 'Europe/Kyiv' } })
    }
    if (url.pathname === '/api/years') return route.fulfill({ json: [2025, 2026, 2027] })
    if (url.pathname === '/api/archive/month') return route.fulfill({ json: { days: [] } })
    if (url.pathname.startsWith('/api/')) {
      return route.fulfill({ status: 404, json: { error: 'forecast_not_published' } })
    }
    return route.continue()
  })
  const page = await context.newPage()
  await page.goto(base.href)
  await page.locator('.wheel-sign').last().waitFor()
  return { page, context }
}

function withinViewport(rect, width, height, inset = 0) {
  assert.ok(rect.left >= inset - .1, `left ${rect.left} < ${inset}`)
  assert.ok(rect.right <= width - inset + .1, `right ${rect.right} > ${width - inset}`)
  assert.ok(rect.top >= inset - .1, `top ${rect.top} < ${inset}`)
  assert.ok(rect.bottom <= height - inset + .1, `bottom ${rect.bottom} > ${height - inset}`)
}

async function targetCenter(sign) {
  const box = await sign.boundingBox()
  assert.ok(box)
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 }
}

for (const [width, height] of [[320, 568], [390, 844], [768, 1024], [1440, 900], [568, 320]]) {
  test(`${width}×${height}: every target, label and tooltip fits throughout rotation`, async () => {
    const { page, context } = await openPage({ width, height })
    try {
      const samples = await page.evaluate(() => {
        const animations = document.querySelector('.wheel-orbit').getAnimations({ subtree: true })
        animations.forEach(animation => animation.pause())
        const samples = []
        for (let time = 0; time < 120000; time += 5000) {
          animations.forEach(animation => { animation.currentTime = time })
          samples.push({
            time,
            scrollWidth: document.documentElement.scrollWidth,
            boxes: [...document.querySelectorAll('.wheel-sign')].map(el => ({
              target: el.getBoundingClientRect().toJSON(),
              label: el.querySelector('small').getBoundingClientRect().toJSON(),
            })),
          })
        }
        animations.forEach(animation => { animation.currentTime = 0 })
        return samples
      })
      assert.ok(samples[0].boxes.length > 0)
      for (const sample of samples) {
        assert.equal(sample.scrollWidth, width)
        for (const { target, label } of sample.boxes) {
          withinViewport(target, width, height, 2) // Include the focus ring.
          withinViewport(label, width, height)
          assert.ok(target.width >= 55.9 && target.height >= 55.9)
          assert.ok(label.left >= target.left - .1 && label.right <= target.right + .1)
        }
      }
      if (width >= 768 && height >= 768) {
        const aries = samples[0].boxes[0].target
        assert.equal(aries.width, 96)
        assert.equal(height / 2 - (aries.top + aries.height / 2), 240)
      }
      const signs = page.locator('.wheel-sign')
      for (const time of [0, 45000, 90000]) {
        // Clear the previous hover before jumping the entire orbit to a new time.
        await page.mouse.move(0, 0)
        await page.waitForFunction(() => !document.querySelector('.wheel-tooltip-orbit'))
        await page.evaluate(time => {
          document.querySelector('.wheel-orbit').getAnimations({ subtree: true })
            .forEach(animation => { animation.currentTime = time })
        }, time)
        for (let index = 0; index < await signs.count(); index++) {
          await signs.nth(index).hover()
          await page.waitForFunction(() => !document.querySelector('.tip-enter-active, .tip-leave-active'))
          const tooltip = page.locator('.wheel-tooltip-orbit:visible, .wheel-tooltip-center:visible')
          assert.equal(await tooltip.count(), 1)
          withinViewport(await tooltip.evaluate(el => el.getBoundingClientRect().toJSON()), width, height)
          assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), width)
        }
      }
    } finally {
      await context.close()
    }
  })
}

test('rotation and counter-rotation advance, pause together on hover, then resume', async () => {
  const { page, context } = await openPage({ width: 390, height: 844 })
  try {
    const orbit = page.locator('.wheel-orbit')
    const transform = await orbit.evaluate(el => getComputedStyle(el).transform)
    await page.waitForFunction(previous => getComputedStyle(document.querySelector('.wheel-orbit')).transform !== previous, transform)
    // Move the real pointer to a moving target; locator.hover waits for a
    // stationary box before moving, which an intentionally rotating wheel lacks.
    const point = await targetCenter(page.locator('.wheel-sign').first())
    await page.mouse.move(point.x, point.y)
    const states = await page.locator('.wheel-orbit, .wheel-sign').evaluateAll(elements => elements.map(el => getComputedStyle(el).animationPlayState))
    assert.ok(states.every(state => state === 'paused'))
    const paused = await orbit.evaluate(el => el.getAnimations()[0].currentTime)
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
    assert.equal(await orbit.evaluate(el => el.getAnimations()[0].currentTime), paused)
    await page.mouse.move(0, 0)
    await page.waitForFunction(previous => document.querySelector('.wheel-orbit').getAnimations()[0].currentTime > previous, paused)
    assert.ok((await page.locator('.wheel-sign').evaluateAll(elements => elements.map(el => getComputedStyle(el).animationPlayState))).every(state => state === 'running'))
  } finally {
    await context.close()
  }
})

test('keyboard focus survives resize; click, Enter and Space retain selection', async () => {
  const { page, context } = await openPage({ width: 1440, height: 900 })
  try {
    await page.keyboard.press('Tab')
    assert.equal(await page.locator(':focus').getAttribute('id'), 'language-select')
    await page.keyboard.press('Tab')
    const focusedName = await page.locator(':focus small').textContent()
    assert.equal(focusedName, 'Aries')
    for (const [width, height] of [[320, 568], [390, 844], [768, 1024], [1440, 900]]) {
      await page.setViewportSize({ width, height })
      assert.equal(await page.locator(':focus small').textContent(), focusedName)
      const details = page.locator('.wheel-tooltip-orbit:visible, .wheel-tooltip-center:visible')
      assert.equal(await details.locator('h3').textContent(), focusedName)
      assert.equal(await details.locator('p').first().textContent(), await page.locator(':focus').getAttribute('aria-description'))
      const rect = await page.locator(':focus').evaluate(el => el.getBoundingClientRect().toJSON())
      withinViewport(rect, width, height, 2)
      assert.notEqual(await page.locator(':focus').evaluate(el => getComputedStyle(el).boxShadow), 'none')
    }
    for (const action of ['Enter', 'Space', 'click']) {
      await page.goto(base.href)
      const sign = page.locator('.wheel-sign').filter({ has: page.locator('small', { hasText: /^Ophiuchus$/ }) })
      await sign.waitFor()
      if (action === 'click') {
        const point = await targetCenter(sign)
        await page.mouse.click(point.x, point.y)
      }
      else {
        await sign.focus()
        await page.keyboard.press(action)
      }
      await page.waitForURL('**/horoscope/ophiuchus/2026-11-15')
      assert.equal(await page.locator('.wheel-orbit').count(), 0)
      assert.equal(await page.evaluate(() => document.getAnimations().filter(animation => ['spin', 'spinReverse'].includes(animation.animationName)).length), 0)
    }
  } finally {
    await context.close()
  }
})

test('touch tap selects a sign at 320px', async () => {
  const { page, context } = await openPage({ width: 320, height: 568 }, { hasTouch: true, isMobile: true })
  try {
    const point = await targetCenter(page.locator('.wheel-sign').filter({ has: page.locator('small', { hasText: /^Sagittarius$/ }) }))
    await page.touchscreen.tap(point.x, point.y)
    await page.waitForURL('**/horoscope/sagittarius/2026-11-15')
  } finally {
    await context.close()
  }
})

test('Wheel and Starfield follow reduced motion on entry and while Home is open', async () => {
  const { page, context } = await openPage({ width: 390, height: 844 }, { reducedMotion: 'reduce' })
  try {
    for (const preference of ['reduce', 'no-preference', 'reduce']) {
      await page.emulateMedia({ reducedMotion: preference })
      const reduced = preference === 'reduce'
      await page.waitForFunction(reduced =>
        [...document.querySelectorAll('.wheel-orbit, .wheel-sign')].every(el =>
          (getComputedStyle(el).animationName === 'none') === reduced
        ), reduced)
      const canvasChanged = await page.locator('canvas').evaluate(async canvas => {
        const frame = () => new Promise(resolve => requestAnimationFrame(resolve))
        await frame()
        const before = canvas.toDataURL()
        await frame()
        await frame()
        return canvas.toDataURL() !== before
      })
      assert.equal(canvasChanged, !reduced)
    }

    await page.keyboard.press('Tab')
    assert.equal(await page.locator(':focus').getAttribute('id'), 'language-select')
    await page.keyboard.press('Tab')
    assert.equal(await page.locator('.wheel-tooltip-center:visible h3').textContent(), 'Aries')
    await page.keyboard.press('Space')
    await page.waitForURL('**/horoscope/aries/2026-11-15')
    assert.equal(await page.locator('canvas, .wheel-orbit').count(), 0)
  } finally {
    await context.close()
  }
})

test('archive month and year arrows have names, visible keyboard focus and working activation', async () => {
  const { page, context } = await openPage({ width: 390, height: 844 })
  try {
    await page.goto(new URL('/archive/aries/2026/11', base).href)
    const controls = [
      ['Previous year', 'Enter', '2025/11'],
      ['Next year', 'Space', '2026/11'],
      ['Previous month', 'Space', '2026/10'],
      ['Next month', 'Enter', '2026/11'],
    ]
    for (const [name, key, month] of controls) {
      const button = page.getByRole('button', { name, exact: true })
      await button.waitFor()
      // Tab through preceding controls as well, including any calendar links.
      for (let i = 0; i < 50 && !(await button.evaluate(el => el === document.activeElement)); i++) {
        await page.keyboard.press('Tab')
      }
      assert.ok(await button.evaluate(el => el.matches(':focus-visible')))
      assert.ok(await button.evaluate(el => {
        const style = getComputedStyle(el)
        return style.outlineStyle === 'solid' && parseFloat(style.outlineWidth) >= 2
      }))
      await page.keyboard.press(key)
      await page.waitForURL('**/archive/aries/' + month)
    }
  } finally {
    await context.close()
  }
})
