// These deterministic tests exercise the HTTP/artifact boundary. Browser capture of
// the real Vue bundle is a separate acceptance check, not mocked by these tests.
import { test, before, after } from 'node:test'
import assert from 'node:assert/strict'
import { JSDOM } from 'jsdom'
import { createPoc, loadShared } from './server.mjs'

const forecast = '/horoscope/gemini/2026-06-26'
const archive = '/archive/gemini/2026/06'
const unrelated = '/horoscope/ophiuchus/2026-05-28'
let poc, origin, shared, failBackend = false
before(async () => {
  shared = await loadShared()
  poc = await createPoc({ shared, fixture: true, source: async path => {
    if (failBackend) throw new Error('Isolated backend failure')
    const url = new URL(path, 'http://fixture.invalid')
    if (url.pathname === '/api/meta') return { status: 200, body: { business_date: '2026-09-30', timezone: 'Europe/Kyiv' } }
    if (url.pathname === '/api/forecast') return url.searchParams.get('sign') === 'aries'
      ? { status: 404, body: { error: 'forecast_not_published' } }
      : { status: 200, body: { text: 'Original published text' } }
    if (url.pathname === '/api/archive/month') return { status: 200, body: { days: [6, 7, 26, 27, 28, 29].map(d => ({ date: `2026-06-${String(d).padStart(2, '0')}`, has_forecast: true })) } }
    throw new Error(`Unexpected fixture read ${path}`)
  } })
  origin = await poc.listen(0)
})
after(async () => poc.close())
const get = path => fetch(origin + path, { redirect: 'manual' })
async function post(path, body = {}) {
  const r = await fetch(origin + '/__poc/' + path, { method: 'POST', body: JSON.stringify(body) })
  assert.equal(r.status, 200, await r.clone().text())
  return r.json()
}
async function capture(jobs) {
  for (const job of jobs) {
    const info = await poc.inspect(job.path)
    const content = info.status === 404 ? 'Прогноз ещё не опубликован' : info.route.kind === 'forecast' ? info.response.body.text : info.route.kind === 'archive'
      ? info.response.body.days.filter(d => d.has_forecast).map(d => `<a href="/horoscope/gemini/${d.date}">${d.date}</a>`).join('')
      : info.response.body.business_date
    await post('capture', { token: job.token, title: job.path, markup: `<div id="app"><h1>${job.path}</h1><p>${content}</p></div>`, businessDate: (await poc.inspect('/')).response.body.business_date, apiResponse: info.response })
  }
}
const rows = () => new Map(poc.state().artifacts.map(a => [a.path, a]))

test('published HTTP HTML, canonical, assets and shared Ophiuchus validation', async () => {
  await capture(await post('refresh', { paths: ['/', forecast, archive, unrelated] }))
  const response = await get(forecast), html = await response.text()
  assert.equal(response.status, 200)
  assert.match(response.headers.get('content-type'), /text\/html/)
  assert.match(html, /Original published text/)
  assert.ok(html.includes(`rel="canonical" href="${origin}${forecast}"`))
  assert.match(html, /<html lang="uk">/)
  assert.equal((await get(unrelated)).status, 200)
  assert.equal((await get('/__poc/client.js')).status, 200)
})
test('unpublished and invalid routes are real 404s; no fallback/clamping', async () => {
  for (const path of ['/horoscope/aries/2026-09-28', '/horoscope/not-a-sign/2026-06-26', '/horoscope/gemini/2026-02-30', '/unknown', '/archive/aries/2026/13/01']) {
    const response = await get(path)
    assert.equal(response.status, 404, path)
    assert.equal(response.headers.get('location'), null)
    assert.doesNotMatch(await response.text(), /Original published text/)
  }
})
test('legacy migration is HTTP 301; one-digit components retain existing normalization', async () => {
  for (const path of ['/archive/gemini/2026/06/26', '/archive/gemini/2026/6/26']) {
    const response = await get(path)
    assert.equal(response.status, 301)
    assert.equal(response.headers.get('location'), forecast)
  }
})
test('archive raw HTML contains only available navigation', async () => {
  const html = await (await get(archive)).text()
  for (const d of ['06', '07', '26', '27', '28', '29']) assert.ok(html.includes(`/horoscope/gemini/2026-06-${d}`))
  assert.ok(!html.includes('/horoscope/gemini/2026-06-10'))
})
test('withdrawal cannot serve an old artifact even before explicit refresh', async () => {
  const before = rows()
  await post('fixture', { sign: 'gemini', day: '2026-06-26', text: null })
  const response = await get(forecast)
  assert.equal(response.status, 404)
  assert.doesNotMatch(await response.text(), /Original published text/)
  assert.ok(!poc.artifacts.has(forecast))
  const jobs = await post('forecast', { sign: 'gemini', date: '2026-06-26' })
  assert.deepEqual(jobs.map(j => j.path), [forecast, archive])
  await capture(jobs)
  assert.equal((await get(forecast)).status, 404)
  assert.ok(!(await (await get(archive)).text()).includes(forecast))
  assert.equal(rows().get(unrelated).hash, before.get(unrelated).hash)
  assert.equal(rows().get('/').revision, before.get('/').revision)
})
test('publication refreshes forecast plus archive; content-only update refreshes only forecast', async () => {
  const before = rows()
  await post('fixture', { sign: 'gemini', day: '2026-06-26', text: 'Published A' })
  assert.equal((await get(forecast)).status, 503, 'stale absent snapshot cannot masquerade as current')
  let jobs = await post('forecast', { sign: 'gemini', date: '2026-06-26' })
  assert.deepEqual(jobs.map(j => j.path), [forecast, archive])
  await capture(jobs)
  const archiveRevision = rows().get(archive).revision
  await post('fixture', { sign: 'gemini', day: '2026-06-26', text: 'Updated B' })
  assert.equal((await get(forecast)).status, 503)
  jobs = await post('forecast', { sign: 'gemini', date: '2026-06-26' })
  assert.deepEqual(jobs.map(j => j.path), [forecast])
  await capture(jobs)
  assert.match(await (await get(forecast)).text(), /Updated B/)
  assert.equal(rows().get(archive).revision, archiveRevision)
  assert.equal(rows().get(unrelated).hash, before.get(unrelated).hash)
})
test('date refresh changes Home and archive today navigation, not historical forecasts', async () => {
  const before = rows()
  await post('fixture', { date: '2026-10-01' })
  const jobs = await post('date')
  assert.deepEqual(jobs.map(j => j.path), ['/', archive])
  await capture(jobs)
  assert.match(await (await get('/')).text(), /2026-10-01/)
  assert.equal(rows().get(forecast).hash, before.get(forecast).hash)
  assert.equal(rows().get(unrelated).revision, before.get(unrelated).revision)
})
test('publication changing during capture rejects the stale result', async () => {
  const [job] = await post('refresh', { paths: [forecast] })
  await post('fixture', { sign: 'gemini', day: '2026-06-26', text: null })
  const response = await fetch(origin + '/__poc/capture', { method: 'POST', body: JSON.stringify({ token: job.token, markup: '<div id="app">old text</div>' }) })
  assert.equal(response.status, 409)
  assert.equal((await get(forecast)).status, 404)
})
test('a date jump also refreshes labels relative to the old business date', async () => {
  const oldToday = '/horoscope/gemini/2026-10-01'
  await capture(await post('refresh', { paths: [oldToday] }))
  const before = rows()
  await post('fixture', { date: '2026-10-10' })
  const jobs = await post('date')
  assert.deepEqual(jobs.map(j => j.path), ['/', archive, oldToday])
  await capture(jobs)
  assert.equal(rows().get(unrelated).hash, before.get(unrelated).hash)
})
test('business date changing during capture rejects stale date-dependent output', async () => {
  const [job] = await post('refresh', { paths: [archive] })
  await post('fixture', { date: '2026-10-11' })
  const response = await fetch(origin + '/__poc/capture', { method: 'POST', body: JSON.stringify({ token: job.token, markup: '<div id="app">old date</div>', businessDate: '2026-10-10', apiResponse: (await poc.inspect(archive)).response }) })
  assert.equal(response.status, 409)
  assert.equal((await get(archive)).status, 503)
})
test('an old refresh ticket cannot overwrite a newer capture', async () => {
  const [old] = await post('refresh', { paths: [forecast] })
  await capture(await post('refresh', { paths: [forecast] }))
  const response = await fetch(origin + '/__poc/capture', { method: 'POST', body: JSON.stringify({ token: old.token, markup: '<div id="app">old text</div>' }) })
  assert.equal(response.status, 409)
})
test('capture must identify the actual current API response rendered by Vue', async () => {
  const [job] = await post('refresh', { paths: [unrelated] })
  const response = await fetch(origin + '/__poc/capture', { method: 'POST', body: JSON.stringify({ token: job.token, markup: '<div id="app">wrong content</div>', apiResponse: { status: 200, body: { text: 'Different response' } }, businessDate: '2026-10-11' }) })
  assert.equal(response.status, 409)
  assert.ok(!poc.artifacts.has(unrelated))
})
test('backend failure is 503, not unpublished 404; non-read API routes are inaccessible', async () => {
  failBackend = true
  assert.equal((await get('/horoscope/taurus/2026-07-01')).status, 503)
  assert.equal((await get('/api/admin/generate')).status, 404)
  failBackend = false
})

// Independent, uncached response sources allow deterministic races and changes to
// real month-envelope fields. No Flask requests or database writes are made.
function deferred() {
  let resolve
  const promise = new Promise(r => { resolve = r })
  return { promise, resolve }
}
const escapeHtml = text => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
async function isolated(t) {
  const data = { text: 'Published A', dates: ['2026-06-26'], count: 1, businessDate: '2026-10-01' }
  let barrier
  const barriers = []
  const local = await createPoc({ shared, source: async path => {
    const name = new URL(path, 'http://fixture.invalid').pathname
    let response
    if (name === '/api/meta') response = { status: 200, body: { business_date: data.businessDate, timezone: 'Europe/Kyiv' } }
    else if (name === '/api/forecast') response = data.text === null
      ? { status: 404, body: { error: 'forecast_not_published' } }
      : { status: 200, body: { text: data.text } }
    else if (name === '/api/archive/month') response = { status: 200, body: {
      year: 2026, month: 6, expected_sign_count: 13,
      days: [26, 27].map(day => ({ date: `2026-06-${day}`, has_forecast: data.dates.includes(`2026-06-${day}`), forecast_count: data.count, missing_count: 13 - data.count })),
    } }
    else throw new Error(`Unexpected source path ${path}`)
    if (barrier?.path === name) {
      const held = barrier
      barrier = null
      held.entered.resolve()
      await held.release.promise
    }
    return response
  } })
  const base = await local.listen(0)
  t.after(async () => { barriers.forEach(b => b.release.resolve()); await local.close() })
  const post = (name, body = {}) => fetch(base + '/__poc/' + name, { method: 'POST', body: JSON.stringify(body) })
  return {
    local, data, post,
    get: path => fetch(base + path, { redirect: 'manual' }),
    hold(path) {
      barrier = { path, entered: deferred(), release: deferred() }
      barriers.push(barrier)
      return barrier
    },
    async payload(job, title = 'Capture') {
      const info = await local.inspect(job.path)
      const content = info.route.kind === 'archive'
        ? info.response.body.days.filter(d => d.has_forecast).map(d => d.date).join(',')
        : info.response?.body.text ?? 'Unavailable'
      return { token: job.token, title, markup: `<div id="app"><h1>${escapeHtml(title)}</h1><article>${escapeHtml(content)}</article></div>`, businessDate: data.businessDate, apiResponse: info.response }
    },
    async accept(job, title) {
      const response = await post('capture', await this.payload(job, title))
      assert.equal(response.status, 200, await response.text())
    },
  }
}

test('regression: overlapping refresh A cannot create a ticket after B is captured', { timeout: 5000 }, async t => {
  const h = await isolated(t)
  const held = h.hold('/api/forecast')
  const older = h.local.refresh([forecast])
  await held.entered.promise
  const [newer] = await h.local.refresh([forecast])
  await h.accept(newer, 'Newer B')
  const expected = h.local.state().artifacts
  held.release.resolve()
  assert.deepEqual(await older, [], 'obsolete inspection must not create an active ticket')
  assert.equal((await h.post('capture', { token: 'obsolete-A', markup: '<div id="app">A</div>' })).status, 409)
  assert.deepEqual(h.local.state().artifacts, expected)
  assert.deepEqual(h.local.state().pending, [])
  assert.match(await (await h.get(forecast)).text(), /Newer B/)
  const [next] = await h.local.refresh([forecast])
  await h.accept(next, 'Sequential C')
  assert.match(await (await h.get(forecast)).text(), /Sequential C/)
})

for (const endpoint of ['forecast', 'date']) {
  test(`regression: ${endpoint} planner cannot invalidate a newer capture after preflight`, { timeout: 5000 }, async t => {
    const h = await isolated(t), path = endpoint === 'forecast' ? forecast : '/'
    const held = h.hold(endpoint === 'forecast' ? '/api/archive/month' : '/api/meta')
    const older = h.post(endpoint, { sign: 'gemini', date: '2026-06-26' })
    await held.entered.promise
    const [newer] = await h.local.refresh([path])
    await h.accept(newer, 'Newer B')
    const expected = h.local.artifacts.get(path)
    held.release.resolve()
    const response = await older
    assert.equal(response.status, 200)
    assert.ok(!(await response.json()).some(job => job.path === path))
    assert.equal(h.local.artifacts.get(path), expected)
    assert.match(await (await h.get(path)).text(), /Newer B/)
  })
}

for (const boundary of ['/api/forecast', '/api/meta']) {
  test(`regression: capture superseded while awaiting ${boundary} rejects with 409`, { timeout: 5000 }, async t => {
    const h = await isolated(t)
    const [old] = await h.local.refresh([forecast])
    const payload = await h.payload(old, 'Older A')
    const held = h.hold(boundary)
    const submitted = h.post('capture', payload)
    await held.entered.promise
    const [newer] = await h.local.refresh([forecast])
    await h.accept(newer, 'Newer B')
    const expected = h.local.artifacts.get(forecast)
    held.release.resolve()
    assert.equal((await submitted).status, 409)
    assert.equal(h.local.artifacts.get(forecast), expected)
    assert.match(await (await h.get(forecast)).text(), /Newer B/)
  })
}

test('regression: a pending GET cannot discard a newer refreshed artifact', { timeout: 5000 }, async t => {
  const h = await isolated(t)
  const [first] = await h.local.refresh([forecast])
  await h.accept(first)
  const held = h.hold('/api/forecast'), pendingGet = h.get(forecast)
  await held.entered.promise
  h.data.text = 'Updated B'
  const [newer] = await h.local.refresh([forecast])
  await h.accept(newer)
  const expected = h.local.artifacts.get(forecast)
  held.release.resolve()
  assert.equal((await pendingGet).status, 503)
  assert.equal(h.local.artifacts.get(forecast), expected)
  assert.match(await (await h.get(forecast)).text(), /Updated B/)
})

test('regression: replacement tokens remain literal in captured markup, title and metadata', async t => {
  const h = await isolated(t)
  const literal = "Literal $& / $' / $` / $$ forecast text"
  h.data.text = literal
  const [job] = await h.local.refresh([forecast])
  const payload = await h.payload(job, literal)
  assert.equal((await h.post('capture', payload)).status, 200)
  const response = await h.get(forecast), html = await response.text()
  assert.equal(response.status, 200)
  assert.ok(html.includes(payload.markup), 'captured HTML must be inserted byte-for-byte')
  const dom = new JSDOM(html)
  assert.equal(dom.window.document.querySelector('article').textContent, literal)
  assert.equal(dom.window.document.title, literal)
  assert.equal(dom.window.document.querySelectorAll('#app').length, 1)
  assert.equal(dom.window.document.querySelectorAll('#poc-options').length, 1)
  dom.window.close()
  // Invalid routes also carry dynamic path data in the bootstrap metadata.
  const path = '/literal-$&', [invalid] = await h.local.refresh([path])
  await h.accept(invalid, literal)
  const invalidDom = new JSDOM(await (await h.get(path)).text())
  assert.equal(JSON.parse(invalidDom.window.document.querySelector('#poc-options').textContent).path, path)
  invalidDom.window.close()
})

test('regression: aggregate-only month changes preserve archive serving and capture validity', async t => {
  const h = await isolated(t)
  const [job] = await h.local.refresh([archive])
  const payload = await h.payload(job)
  h.data.count = 2
  assert.equal((await h.post('capture', payload)).status, 200, 'unused aggregates do not invalidate an in-flight capture')
  const expected = h.local.artifacts.get(archive)
  h.data.count = 3
  const planned = await h.post('forecast', { sign: 'gemini', date: '2026-06-26' })
  assert.deepEqual((await planned.json()).map(job => job.path), [forecast])
  const response = await h.get(archive)
  assert.equal(response.status, 200)
  assert.equal(response.headers.get('cache-control'), 'no-store')
  assert.equal(h.local.artifacts.get(archive), expected)
})

test('regression: archive presentation changes refresh on publication/withdrawal, not text updates', async t => {
  const h = await isolated(t)
  await h.accept((await h.local.refresh([archive]))[0])
  for (const dates of [['2026-06-26', '2026-06-27'], ['2026-06-26']]) {
    h.data.dates = dates
    const planned = await h.post('forecast', { sign: 'gemini', date: '2026-06-27' })
    const jobs = await planned.json()
    assert.deepEqual(jobs.map(job => job.path), ['/horoscope/gemini/2026-06-27', archive])
    assert.equal((await h.get(archive)).status, 503)
    for (const job of jobs) await h.accept(job)
    const response = await h.get(archive)
    assert.equal(response.status, 200)
    assert.equal((await response.text()).includes('2026-06-27'), dates.includes('2026-06-27'))
  }
  const expected = h.local.artifacts.get(archive)
  h.data.text = 'Updated content only'
  const planned = await h.post('forecast', { sign: 'gemini', date: '2026-06-26' })
  const jobs = await planned.json()
  assert.deepEqual(jobs.map(job => job.path), [forecast])
  await h.accept(jobs[0])
  assert.equal((await h.get(archive)).status, 200)
  assert.equal(h.local.artifacts.get(archive), expected)
  // Unlike aggregate changes, a different rendered availability set is rejected.
  const [job] = await h.local.refresh([archive]), payload = await h.payload(job)
  h.data.dates = ['2026-06-27']
  assert.equal((await h.post('capture', payload)).status, 409)
})
