// Disposable loopback-only experiment. Not a production server or publication store.
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createHash, randomUUID } from 'node:crypto'
import { build } from 'vite'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
const digest = value => createHash('sha256').update(value).digest('hex')
const escape = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
const json = value => JSON.stringify(value).replace(/</g, '\\u003c')
const forecastApi = (sign, date) => `/api/forecast?${new URLSearchParams({ sign, date })}`
const monthPath = (sign, date) => `/archive/${sign}/${date.slice(0, 4)}/${date.slice(5, 7)}`
// Match the archive API consumer: only valid, explicitly available dates render links.
// Aggregate coverage counts are not used by ArchiveMonth.
const availability = response => {
  if (!Array.isArray(response?.body?.days)) throw new Error('Invalid archive month response')
  return [...new Set(response.body.days.filter(day => {
    if (day?.has_forecast !== true || typeof day.date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(day.date)) return false
    const timestamp = Date.parse(`${day.date}T00:00:00Z`)
    return Number.isFinite(timestamp) && new Date(timestamp).toISOString().slice(0, 10) === day.date
  }).map(day => day.date))].sort()
}
const fingerprint = (route, response) => digest(json(route.kind === 'archive'
  ? { status: response.status, dates: availability(response) } : response))

export async function loadShared() {
  // Compile existing TS using the already-declared Vite dependency, without output files.
  const result = await build({ root, configFile: false, logLevel: 'silent', build: {
    write: false, minify: false, lib: { entry: resolve(here, 'shared.ts'), formats: ['es'] },
  } })
  const output = Array.isArray(result) ? result[0] : result
  return import(`data:text/javascript;base64,${Buffer.from(output.output[0].code).toString('base64')}`)
}

export async function createPoc({ backend = 'http://localhost:8000', fixture = false, source, shared } = {}) {
  shared ??= await loadShared()
  const template = await readFile(resolve(root, 'dist/index.html'), 'utf8')
  const main = template.match(/<script type="module"[^>]*src="([^"]+)"[^>]*><\/script>/)?.[1]
  if (!main) throw new Error('Run npm run build first')
  const artifacts = new Map(), tickets = new Map(), overrides = new Map(), fixtureReads = new Map()
  const generations = new Map()
  let fixtureDate, revision = 0, refreshGeneration = 0, origin
  const upstream = source ?? (async path => {
    const response = await fetch(new URL(path, backend), { signal: AbortSignal.timeout(5000) })
    return { status: response.status, body: await response.json() }
  })
  async function api(path) {
    let value
    if (fixture && fixtureReads.has(path)) value = structuredClone(fixtureReads.get(path))
    else {
      value = await upstream(path)
      if (fixture) fixtureReads.set(path, structuredClone(value))
      value = structuredClone(value)
    }
    const url = new URL(path, 'http://poc.invalid'), q = url.searchParams
    if (fixture && url.pathname === '/api/meta' && fixtureDate) value.body.business_date = fixtureDate
    if (fixture && url.pathname === '/api/forecast') {
      const key = `${q.get('sign')}/${q.get('date')}`
      if (overrides.has(key)) {
        const text = overrides.get(key)
        value = text === null ? { status: 404, body: { error: 'forecast_not_published' } }
          : { status: 200, body: { text } }
      }
    }
    if (fixture && url.pathname === '/api/archive/month' && value.status === 200) {
      for (const day of value.body.days) {
        const key = `${q.get('sign')}/${day.date}`
        if (overrides.has(key)) day.has_forecast = overrides.get(key) !== null
      }
    }
    return value
  }
  function classify(path) {
    if (path === '/') return { kind: 'home' }
    let m = /^\/horoscope\/([^/]+)\/([^/]+)$/.exec(path)
    if (m) {
      const v = shared.validateHoroscopeRoute({ sign: m[1], day: m[2] })
      return v.ok ? { kind: 'forecast', ...v.params } : { kind: 'invalid' }
    }
    m = /^\/archive\/([^/]+)\/([^/]+)\/([^/]+)(?:\/([^/]+))?$/.exec(path)
    if (m) {
      const v = (m[4] ? shared.validateArchiveForecastRoute : shared.validateArchiveMonthRoute)({ sign: m[1], year: m[2], month: m[3], day: m[4] })
      if (!v.ok) return { kind: 'invalid' }
      const { sign, year, month, day } = v.params
      if (m[4]) return { kind: 'redirect', location: `/horoscope/${sign}/${String(year).padStart(4, '0')}-${shared.pad2(month)}-${shared.pad2(day)}` }
      return { kind: 'archive', sign, year, month }
    }
    return { kind: 'invalid' }
  }
  async function inspect(path) {
    const route = classify(path)
    if (route.kind === 'invalid') return { route, status: 404 }
    if (route.kind === 'redirect') return { route, status: 301 }
    const apiPath = route.kind === 'home' ? '/api/meta' : route.kind === 'forecast'
      ? forecastApi(route.sign, route.day)
      : `/api/archive/month?${new URLSearchParams({ year: String(route.year), month: String(route.month), sign: route.sign, locale: 'ru', type: 'daily' })}`
    const response = await api(apiPath)
    // The exact backend absence contract authorizes 404; all other failures fail closed.
    const absent = route.kind === 'forecast' && response.status === 404 && response.body.error === 'forecast_not_published'
    if (response.status !== 200 && !absent) throw new Error(`Backend unavailable: ${apiPath} (${response.status})`)
    return { route, status: absent ? 404 : 200, apiPath, response, fingerprint: fingerprint(route, response) }
  }
  function page(path, info, markup = '', capture = null) {
    const options = { main, path, capture, apiPath: info.apiPath, kind: info.route.kind, signs: shared.HOME_ZODIACS, fixture }
    return template.replace(/<script type="module"[^>]*><\/script>/, () => `<script id="poc-options" type="application/json">${json(options)}</script><script type="module" src="/__poc/client.js"></script>`)
      .replace('<div id="app"></div>', () => markup || '<div id="app"></div>')
      .replace('<title>Horoscope App</title>', () => `<title>${escape(info.title || 'Horoscope App')}</title>${info.status === 200 ? `<link rel="canonical" href="${escape(origin + path)}">` : '<meta name="robots" content="noindex">'}`)
  }
  function claim(paths, generation) {
    // A planner may discover a dependency after awaiting Flask. It cannot claim a
    // route already claimed by a newer operation, even if that capture finished.
    for (const path of paths) {
      if ((generations.get(path) ?? 0) > generation) continue
      generations.set(path, generation)
      for (const [token, ticket] of tickets) if (ticket.path === path && ticket.generation !== generation) tickets.delete(token)
    }
  }
  async function refresh(paths, generation = ++refreshGeneration) {
    if (paths.length > 10) throw new Error('POC limited to ten routes per explicit batch')
    for (const path of paths) {
      if (!path.startsWith('/') || path.startsWith('//') || path.includes('?') || path.includes('#')) throw new Error('Use an exact local pathname')
    }
    claim(paths, generation)
    const current = path => generations.get(path) === generation
    // Invalidate first: failed capture cannot leave a previously published file serving.
    for (const path of paths) {
      if (current(path)) artifacts.delete(path)
    }
    const jobs = []
    for (const path of [...new Set(paths)]) {
      if (!current(path)) continue
      const info = await inspect(path)
      if (!current(path) || info.status === 301) continue
      const token = randomUUID()
      tickets.set(token, { path, info, generation })
      jobs.push({ path, token })
    }
    return jobs
  }
  async function refreshForecast(sign, date) {
    if (!shared.validateHoroscopeRoute({ sign, day: date }).ok) throw new Error('Invalid forecast scope')
    const path = `/horoscope/${sign}/${date}`, archive = monthPath(sign, date)
    const generation = ++refreshGeneration
    claim([path, archive], generation)
    const current = await inspect(archive), previous = artifacts.get(archive)
    const paths = [path]
    if (!previous || previous.info.fingerprint !== current.fingerprint) paths.push(archive)
    return refresh(paths, generation)
  }
  function state() {
    return { fixture, artifacts: [...artifacts].map(([path, a]) => ({ path, status: a.info.status, revision: a.revision, hash: digest(a.html) })), pending: [...tickets.values()].map(t => t.path) }
  }
  const server = createServer(async (req, res) => {
    const send = (status, body, type = 'application/json', headers = {}) => {
      res.writeHead(status, { 'Content-Type': type, 'Cache-Control': 'no-store', ...headers }); res.end(body)
    }
    try {
      const url = new URL(req.url, origin), path = url.pathname
      if (req.method === 'POST') {
        if (!path.startsWith('/__poc/') || (req.headers.origin && req.headers.origin !== origin)) return send(403, '{}')
        let raw = ''
        for await (const chunk of req) { raw += chunk; if (raw.length > 2_000_000) throw new Error('Payload too large') }
        const body = JSON.parse(raw || '{}')
        if (path === '/__poc/capture') {
          const ticket = tickets.get(body.token)
          if (!ticket || generations.get(ticket.path) !== ticket.generation) return send(409, json({ error: 'Expired capture' }))
          const latest = await inspect(ticket.path)
          if (latest.fingerprint !== ticket.info.fingerprint) { tickets.delete(body.token); return send(409, json({ error: 'Publication changed during capture' })) }
          if (latest.apiPath && fingerprint(latest.route, body.apiResponse ?? null) !== latest.fingerprint) return send(409, json({ error: 'Rendered API response is not current' }))
          if (typeof body.markup !== 'string' || !body.markup.startsWith('<div id="app"')) throw new Error('Invalid capture root')
          const businessDate = (await api('/api/meta')).body.business_date
          if (body.businessDate !== businessDate) { tickets.delete(body.token); return send(409, json({ error: 'Business date changed during capture' })) }
          if (tickets.get(body.token) !== ticket || generations.get(ticket.path) !== ticket.generation) return send(409, json({ error: 'Capture superseded while validating' }))
          const info = { ...latest, title: body.title, businessDate }
          artifacts.set(ticket.path, { info, html: page(ticket.path, info, body.markup), revision: ++revision })
          tickets.delete(body.token)
          return send(200, json(state()))
        }
        if (path === '/__poc/refresh') return send(200, json(await refresh(body.paths)))
        if (path === '/__poc/forecast') return send(200, json(await refreshForecast(body.sign, body.date)))
        if (path === '/__poc/date') {
          // Archives contain a "today" link; refresh those too, but not historical forecasts.
          const generation = ++refreshGeneration
          claim(['/'], generation)
          const day = (await api('/api/meta')).body.business_date
          const paths = ['/']
          for (const [p, a] of artifacts) {
            const route = a.info.route
            const relativeDateChanges = route.kind === 'forecast' && [day, a.info.businessDate].some(d => Math.abs(Date.parse(route.day) - Date.parse(d)) <= 86400000)
            if (route.kind === 'archive' || relativeDateChanges) paths.push(p)
          }
          return send(200, json(await refresh(paths, generation)))
        }
        if (path === '/__poc/fixture' && fixture) {
          if (body.date) {
            if (!shared.isRealIsoDate(body.date)) throw new Error('Invalid fixture date')
            fixtureDate = body.date
          } else {
            if (!shared.validateHoroscopeRoute({ sign: body.sign, day: body.day }).ok || (body.text !== null && typeof body.text !== 'string')) throw new Error('Invalid fixture forecast')
            overrides.set(`${body.sign}/${body.day}`, body.text)
          }
          return send(200, json({ fixture: true }))
        }
        return send(404, '{}')
      }
      if (req.method !== 'GET') return send(405, '{}')
      if (path === '/__poc/state') return send(200, json(state()))
      if (path === '/__poc') return send(200, await readFile(resolve(here, 'dashboard.html')), 'text/html; charset=utf-8')
      if (path === '/__poc/client.js') return send(200, await readFile(resolve(here, 'client.js')), 'text/javascript')
      if (path === '/__poc/seed') {
        const inventory = await api('/api/seo/sitemap/urls')
        if (inventory.status !== 200) throw new Error('Inventory unavailable')
        const forecast = inventory.body.items.find(i => i.path === '/horoscope/gemini/2026-06-26')
        if (!forecast) throw new Error('Known Gemini fixture is not published; choose another fixture explicitly')
        const ophiuchus = inventory.body.items.find(i => i.type === 'forecast' && i.sign_key === 'ophiuchus')
        return send(200, json({ fixture, paths: ['/', forecast.path, ...(ophiuchus ? [ophiuchus.path] : []), '/archive/gemini/2026/06', '/horoscope/aries/2026-09-28', '/horoscope/not-a-sign/2026-06-26', '/unknown-poc-route'] }))
      }
      if (path.startsWith('/api/')) {
        // Only public read endpoints required by the unchanged SPA/POC, never admin/generation.
        if (!['/api/meta', '/api/forecast', '/api/years', '/api/archive/month'].includes(path)) return send(404, '{}')
        const result = await api(path + url.search)
        return send(result.status, json(result.body))
      }
      if (path.startsWith('/assets/')) {
        if (!/^\/assets\/[\w.-]+$/.test(path)) return send(404, '')
        const type = path.endsWith('.js') ? 'text/javascript' : path.endsWith('.css') ? 'text/css' : 'image/png'
        try { return send(200, await readFile(resolve(root, 'dist', path.slice(1))), type) } catch { return send(404, '') }
      }
      const generation = generations.get(path), observedArtifact = artifacts.get(path)
      const info = await inspect(path)
      // An older GET must not discard an artifact captured while its read awaited Flask.
      if (generations.get(path) !== generation) return send(503, json({ error: 'POC refresh in progress' }))
      if (info.status === 301) return send(301, '', 'text/html', { Location: info.route.location + url.search })
      const capture = url.searchParams.get('__poc_capture'), ticket = tickets.get(capture)
      if (ticket?.path === path) return send(200, page(path, info, '', capture), 'text/html; charset=utf-8')
      const artifact = artifacts.get(path)
      if (artifact && artifact.info.fingerprint === info.fingerprint) return send(info.status, artifact.html, 'text/html; charset=utf-8')
      if (artifact === observedArtifact) artifacts.delete(path)
      if (info.status === 404) return send(404, '<!doctype html><title>Not found</title><h1>Прогноз не опубликован или страница не найдена</h1><a href="/">Главная</a>', 'text/html; charset=utf-8')
      return send(503, '<!doctype html><title>POC refresh required</title><h1>Explicit POC capture required</h1>', 'text/html; charset=utf-8')
    } catch (error) { send(503, json({ error: error.message })) }
  })
  return { server, state, inspect, refresh, artifacts, async listen(port = 4173) {
    await new Promise(resolve => server.listen(port, '127.0.0.1', resolve))
    origin = `http://127.0.0.1:${server.address().port}`
    return origin
  }, async close() { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)) } }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const poc = await createPoc({ backend: process.env.POC_BACKEND || 'http://localhost:8000', fixture: process.argv.includes('--fixture') })
  console.log(`Disposable ${process.argv.includes('--fixture') ? 'ISOLATED FIXTURE' : 'LIVE READ-ONLY'} POC: ${await poc.listen(Number(process.env.POC_PORT || 4173))}/__poc`)
}
