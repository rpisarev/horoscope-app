// Run against an isolated frontend build. Each API response is a local fixture.
import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const base = new URL(process.env.WHEEL_BASE_URL || 'http://127.0.0.1:54104')
assert.equal(base.hostname, '127.0.0.1')
assert.notEqual(base.port, '5173')

let browser
before(async () => {
  browser = await chromium.launch({
    executablePath: process.env.CHROME_BIN || '/usr/bin/google-chrome',
    args: ['--no-sandbox', '--disable-background-networking'],
  })
})
after(async () => { await browser?.close() })

const languages = [
  { locale: 'en', previous: 'Previous day', nextSign: 'Next sign', today: 'Today' },
  { locale: 'uk', previous: 'Попередній день', nextSign: 'Наступний знак', today: 'Сьогодні' },
  { locale: 'ru', previous: 'Предыдущий день', nextSign: 'Следующий знак', today: 'Сегодня' },
]

function within(inner, outer) {
  assert.ok(inner.left >= outer.left - 0.1 && inner.right <= outer.right + 0.1, JSON.stringify({ inner, outer }))
}

for (const { locale, previous, nextSign, today } of languages) {
  test(`320px ${locale} forecast and archive controls fit and support keyboard sign selection`, async () => {
    const page = await browser.newPage({ viewport: { width: 320, height: 568 }, hasTouch: true })
    const suffix = locale === 'en' ? '' : `?lang=${locale}`
    try {
      await page.route('**/*', route => {
        const url = new URL(route.request().url())
        if (url.origin !== base.origin) return route.abort()
        if (url.pathname === '/api/meta') return route.fulfill({ json: { business_date: '2026-11-22', timezone: 'Europe/Kyiv' } })
        if (url.pathname === '/api/years') return route.fulfill({ json: [2026] })
        if (url.pathname === '/api/archive/month') return route.fulfill({ json: { days: [], locale } })
        if (url.pathname === '/api/forecast') return route.fulfill({ json: { text: 'Fixture', locale } })
        if (url.pathname.startsWith('/api/')) return route.abort()
        return route.continue()
      })

      await page.goto(new URL('/horoscope/aries/2026-11-22' + suffix, base).href)
      const prevDay = page.getByRole('button', { name: previous, exact: true })
      await prevDay.waitFor()
      await page.waitForFunction(today => document.querySelector('article') && document.querySelector('h1')?.textContent.includes(today), today)
      const slider = await prevDay.evaluate(button => {
        const box = element => element.getBoundingClientRect().toJSON()
        const row = button.parentElement
        return { row: box(row), children: [...row.children].map(box) }
      })
      for (const child of slider.children) within(child, slider.row)
      const [back, date, forward] = slider.children
      assert.ok(back.width >= 44 && forward.width >= 44)
      assert.ok(date.left >= back.right && date.right <= forward.left)

      for (const [path, next] of [
        ['/horoscope/aries/2026-11-22', '/horoscope/taurus/2026-11-22'],
        ['/archive/aries/2026/11', '/archive/taurus/2026/11'],
      ]) {
        if (path.startsWith('/archive/')) await page.goto(new URL(path + suffix, base).href)
        const button = page.getByRole('button', { name: nextSign, exact: true })
        await button.waitFor()
        await page.locator('#language-select').focus()
        await page.keyboard.press('Tab')
        await page.keyboard.press('Tab')
        assert.equal(await button.evaluate(el => el === document.activeElement), true)
        await page.keyboard.press('Enter')
        await page.waitForURL(new URL(next + suffix, base).href)

        if (path.startsWith('/horoscope/')) {
          const carousel = page.locator('.swiper').first()
          await page.waitForFunction(() => !document.querySelector('.swiper')?.swiper?.animating)
          const box = await carousel.boundingBox()
          const y = Math.round(box.y + box.height / 2)
          const touch = await page.context().newCDPSession(page)
          await touch.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: 240, y }] })
          for (const x of [210, 180, 150, 120, 90, 60]) {
            await touch.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x, y }] })
          }
          await touch.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
          await touch.detach()
          await page.waitForURL(new URL('/horoscope/gemini/2026-11-22' + suffix, base).href)
        }
      }

      // Sunday is the last column. Its marker and accessible name must fit the cell.
      const cell = page.locator('span[aria-current="date"]')
      await cell.waitFor()
      assert.ok((await cell.textContent()).includes(today))
      const bounds = await cell.evaluate(el => {
        const box = element => element.getBoundingClientRect().toJSON()
        return { cell: box(el), details: [...el.querySelectorAll('span')].map(box) }
      })
      for (const detail of bounds.details) within(detail, bounds.cell)
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 320)
    } finally {
      await page.close()
    }
  })
}
