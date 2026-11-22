// POC-only bootstrap: execute the unchanged production bundle, not a duplicate view.
const options = JSON.parse(document.querySelector('#poc-options').textContent)
const nativeFetch = window.fetch.bind(window)
let pending = 0, lastActivity = performance.now()
const responses = new Map()
window.fetch = async (...args) => {
  const url = new URL(String(args[0]), location.href)
  if (!url.pathname.startsWith('/api/')) return nativeFetch(...args)
  pending++; lastActivity = performance.now()
  try {
    const response = await nativeFetch(...args)
    responses.set(url.pathname + url.search, { status: response.status, body: await response.clone().json() })
    return response
  } finally { pending--; lastActivity = performance.now() }
}

const original = document.querySelector('#app')
const hasSnapshot = original.children.length > 0
if (hasSnapshot) {
  original.id = 'poc-snapshot'
  // Snapshot remains visible but interactive controls wait for the real application.
  original.inert = true
  const stage = document.createElement('div')
  stage.id = 'app'
  stage.style.cssText = 'position:fixed;left:-200vw;top:0;width:100vw;visibility:hidden'
  document.body.append(stage)
}

function homeNavigation(app, day) {
  if (location.pathname !== '/' || app.querySelector('[data-poc-home]')) return
  const section = document.createElement('section')
  section.dataset.pocHome = ''
  section.style.cssText = 'position:relative;z-index:50;background:#020617;color:white;padding:1rem'
  const nav = document.createElement('nav')
  for (const sign of options.signs) {
    const link = document.createElement('a')
    link.textContent = `${sign.glyph} ${sign.name} `
    link.href = `/horoscope/${sign.slug}/${day}`
    nav.append(link)
  }
  section.append(nav)
  app.append(section)
}

try {
  await import(options.main)
  // Bounded render deadline covers the actual initial API calls and Vue DOM updates.
  const deadline = performance.now() + 12000
  while (pending || performance.now() - lastActivity < 200 || !responses.has('/api/meta')) {
    if (performance.now() > deadline) throw new Error('POC initial rendering deadline exceeded')
    await new Promise(resolve => setTimeout(resolve, 30))
  }
  await new Promise(requestAnimationFrame)
  const app = document.querySelector('#app')
  const meta = responses.get('/api/meta')
  if (meta.status !== 200 || !meta.body.business_date) throw new Error('Business metadata unavailable')
  for (const [path, response] of responses) {
    if (path === '/api/signs/meta?locale=en') continue // Home provides local labels if metadata is unavailable.
    if (response.status !== 200 && !(path.startsWith('/api/forecast?') && response.status === 404 && response.body.error === 'forecast_not_published')) throw new Error(`POC cannot capture failed request ${path}`)
  }
  const forecastStatus = app.querySelector('article p.text-amber-200, article p.text-slate-400')?.textContent.trim()
  if (app.querySelector('[role="alert"], [aria-busy="true"]') ||
      forecastStatus === 'Loading forecast…' || forecastStatus === 'Could not load the forecast.') {
    throw new Error('POC refuses loading/error capture')
  }
  homeNavigation(app, meta.body.business_date)
  const siteTitle = document.title
  const title = (app.querySelector('h1')?.textContent.trim().replace(/\s+/g, ' ') || siteTitle) + (options.kind === 'home' ? '' : ` — ${options.path} — ${siteTitle}`)
  document.title = title
  app.removeAttribute('style')
  if (hasSnapshot) original.remove()
  document.documentElement.dataset.pocReady = 'true'
  if (options.capture) {
    const response = await nativeFetch('/__poc/capture', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: options.capture, markup: app.outerHTML, title, businessDate: meta.body.business_date, apiResponse: responses.get(options.apiPath) }) })
    if (!response.ok) throw new Error(await response.text())
    parent.postMessage({ pocCapture: options.capture, path: options.path, ok: true }, location.origin)
    window.fetch = nativeFetch
  } else {
    // The POC adds head tags, so it must not leave them pointing at a previous
    // route after the ordinary SPA navigates. This is not a general meta library.
    const syncHead = () => {
      const path = location.pathname
      const english = document.documentElement.lang === 'en'
      if (!english || path !== '/') app.querySelector('[data-poc-home]')?.remove()
      else homeNavigation(app, responses.get('/api/meta').body.business_date)
      document.title = `${app.querySelector('h1')?.textContent.trim().replace(/\s+/g, ' ') || siteTitle} — ${path}`
      let published = english && path === '/'
      const forecast = /^\/horoscope\/([^/]+)\/([^/]+)$/.exec(path)
      if (english && forecast) published = responses.get(`/api/forecast?${new URLSearchParams({ sign: forecast[1], date: forecast[2], locale: 'en' })}`)?.status === 200
      const archive = /^\/archive\/([^/]+)\/(\d{4})\/(\d{1,2})$/.exec(path)
      if (english && archive) {
        const query = new URLSearchParams({
          year: String(Number(archive[2])), month: String(Number(archive[3])), sign: archive[1], locale: 'en', type: 'daily',
        })
        published = responses.get(`/api/archive/month?${query}`)?.status === 200
      }
      let canonical = document.querySelector('link[rel="canonical"]')
      if (published && !pending) {
        if (!canonical) { canonical = document.createElement('link'); canonical.rel = 'canonical'; document.head.append(canonical) }
        canonical.href = location.origin + path
      } else canonical?.remove()
      let robots = document.querySelector('meta[name="robots"]')
      if (published) robots?.remove()
      else if (!robots) { robots = document.createElement('meta'); robots.name = 'robots'; robots.content = 'noindex'; document.head.append(robots) }
    }
    new MutationObserver(syncHead).observe(app, { childList: true, subtree: true, characterData: true })
  }
} catch (error) {
  window.fetch = nativeFetch
  document.documentElement.dataset.pocError = error.message
  if (options.capture) parent.postMessage({ pocCapture: options.capture, ok: false, error: error.message }, location.origin)
  else {
    // Never quietly replace useful captured content with a loading/error placeholder.
    const notice = document.createElement('p')
    notice.textContent = `POC client startup failed: ${error.message}`
    document.body.append(notice)
  }
}
