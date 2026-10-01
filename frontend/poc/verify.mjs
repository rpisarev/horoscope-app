// Read-only HTTP acceptance check after dashboard capture. JSDOM parses returned
// bytes only: no scripts or browser execution, so this proves initial HTML.
import assert from 'node:assert/strict'
import { JSDOM } from 'jsdom'

const origin = process.env.POC_ORIGIN || 'http://127.0.0.1:4173'
const backend = process.env.POC_BACKEND || 'http://localhost:8000'
async function get(url) {
  return fetch(url, { redirect: 'manual', signal: AbortSignal.timeout(5000) })
}
const meta = await (await get(backend + '/api/meta')).json()
const signs = await (await get(backend + '/api/signs')).json()
const inventory = await (await get(backend + '/api/seo/sitemap/urls')).json()
const ophiuchus = inventory.items.find(i => i.type === 'forecast' && i.sign_key === 'ophiuchus')
assert.ok(ophiuchus, 'Live acceptance requires a verified published Ophiuchus fixture')
const routes = [
  ['/', 200], ['/horoscope/gemini/2026-06-26', 200], [ophiuchus.path, 200],
  ['/archive/gemini/2026/06', 200], ['/horoscope/aries/2026-09-28', 404],
  ['/horoscope/not-a-sign/2026-06-26', 404], ['/unknown-poc-route', 404],
  ['/archive/gemini/2026/06/26', 301],
]
for (const [path, status] of routes) {
  const response = await get(origin + path), html = await response.text()
  assert.equal(response.status, status, path)
  assert.match(response.headers.get('content-type'), /text\/html/)
  if (status === 301) assert.equal(response.headers.get('location'), '/horoscope/gemini/2026-06-26')
  else {
    const dom = new JSDOM(html), document = dom.window.document
    assert.ok(document.querySelector('h1')?.textContent.trim(), path)
    assert.equal(document.documentElement.lang, 'uk', 'POC preserves existing language')
    if (status === 200) assert.equal(document.querySelector('link[rel="canonical"]')?.href, origin + path)
    if (path.startsWith('/horoscope/') && status === 200) {
      const [, , sign, date] = path.split('/')
      const forecast = await (await get(backend + `/api/forecast?${new URLSearchParams({ sign, date })}`)).json()
      assert.ok(document.querySelector('article').textContent.includes(forecast.text), 'Full real backend forecast must exist before JS')
    }
    if (path === '/') {
      assert.equal(signs.length, 13)
      for (const sign of signs) assert.ok(document.querySelector(`a[href="/horoscope/${sign}/${meta.business_date}"]`), sign)
    }
    if (path.startsWith('/archive/')) {
      const links = [...document.querySelectorAll('[aria-label="Календарь архива"] a')].map(a => a.getAttribute('href'))
      assert.deepEqual(links, [6, 7, 26, 27, 28, 29].map(d => `/horoscope/gemini/2026-06-${String(d).padStart(2, '0')}`))
    }
    dom.window.close()
  }
  console.log(JSON.stringify({ path, status, contentType: response.headers.get('content-type'), location: response.headers.get('location'), meaningfulHtml: status !== 301 }))
}
console.log('PASS: eight real-data HTTP/initial-HTML checks; no JavaScript executed')
