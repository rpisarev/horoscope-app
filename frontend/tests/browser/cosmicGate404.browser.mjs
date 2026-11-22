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
  const blocked = new Set()
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => {
    if (message.type() !== 'error') return
    if (blocked.has(message.location().url) && message.text().includes('net::ERR_FAILED')) return
    errors.push(message.text())
  })
  t.after(async () => {
    await page.close()
    assert.deepEqual(errors, [], 'Page or console errors during the 404 visit or recovery')
  })
  await page.route('**/*', route => {
    const url = new URL(route.request().url())
    if (url.origin !== base.origin) {
      blocked.add(url.href)
      return route.abort()
    }
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

// Zero-size landmarks in the membrane's own coordinate system project through
// the browser's camera, including perspective. Read them in one layout pass.
async function apertureContours(gate, radii) {
  return gate.locator(horizon).evaluate((el, radii) => {
    const count = 80
    const points = radii.map(radius => Array.from({ length: count }, (_, i) => {
      const angle = 2 * Math.PI * i / count
      const point = document.createElement('span')
      const left = 50 + 50 * radius * Math.cos(angle)
      const top = 50 + 50 * radius * Math.sin(angle)
      point.style.cssText = `position:absolute;width:0;height:0;left:${left}%;top:${top}%`
      el.append(point)
      return point
    }))
    const contours = points.map(row => row.map(point => {
      const { x, y } = point.getBoundingClientRect()
      return { x, y }
    }))
    points.flat().forEach(point => point.remove())
    return contours
  }, radii)
}

function closestPosition(contour, x, y) {
  // The contour samples equal angles before projection. Interpolate along its
  // closest edge to recover the device's angular position in the gate plane.
  let closest = { distance: Infinity, position: 0 }
  for (const [i, a] of contour.entries()) {
    const b = contour[(i + 1) % contour.length]
    const dx = b.x - a.x
    const dy = b.y - a.y
    const t = Math.min(1, Math.max(0, ((x - a.x) * dx + (y - a.y) * dy) / (dx * dx + dy * dy)))
    const distance = Math.hypot(x - a.x - t * dx, y - a.y - t * dy)
    if (distance < closest.distance) closest = { distance, position: i + t }
  }
  return closest
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
  assert.equal(ring.segments.length, 80, 'The assembled gate has 80 devices')
  assert.equal(ring.designCount, 1, 'Every position uses the same device')
  assert.ok(ring.visible, 'Every device is visible')
  for (const box of ring.segments) {
    assert.ok(box.width > 0 && box.height > 0)
    assert.ok(box.left >= ring.bounds.left && box.right <= ring.bounds.right &&
      box.top >= ring.bounds.top && box.bottom <= ring.bounds.bottom,
      JSON.stringify({ clippedSegment: box, scene: ring.bounds }))
  }
  // A device is centered about half a casting outside the membrane's edge.
  const [rim] = await apertureContours(page.locator(scene), [1.045])
  const half = rim.length / 2
  const diameters = rim.slice(0, half).map((point, i) =>
    Math.hypot(point.x - rim[i + half].x, point.y - rim[i + half].y))
  const major = Math.max(...diameters)
  const minor = Math.min(...diameters)
  const ratio = minor / major
  assert.ok(ratio > .78 && ratio < .93, `Expected a moderately oblique aperture (minor/major ${ratio})`)
  const positions = ring.segments.map(box => {
    const { distance, position } = closestPosition(rim, box.x + box.width / 2, box.y + box.height / 2)
    assert.ok(distance < major * .009, `Device center misses the projected aperture rim by ${distance}px`)
    return position
  }).sort((a, b) => a - b)
  const step = rim.length / positions.length
  positions.forEach((position, i) => {
    const next = positions[i + 1] ?? positions[0] + rim.length
    const gap = (next - position) / step
    assert.ok(gap > .8 && gap < 1.2, `Expected one device per angular step (observed ${gap})`)
  })

  // Sample well inside the aperture, away from the rim lights and surrounding stars.
  const x = (Math.min(...rim.map(p => p.x)) + Math.max(...rim.map(p => p.x))) / 2
  const y = (Math.min(...rim.map(p => p.y)) + Math.max(...rim.map(p => p.y))) / 2
  const size = Math.floor(minor * .45)
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

// Compare the same paused frame with one painted layer hidden. The atlas box is
// fixed throughout the shot, so its DOM bounds cannot measure the water's reach.
async function paintedFootprint(gate, selector) {
  const sceneBox = await gate.boundingBox()
  // Express the same rim band and outside clearance in aperture radii.
  const contours = await apertureContours(gate, [.98, 1.14, 1.21])
  const shown = await gate.screenshot({ scale: 'css' })
  const hidden = await gate.screenshot({ scale: 'css', style: selector + ' { visibility: hidden !important; }' })
  return gate.evaluate(async (_, { frames, contours, sceneBox }) => {
    const [a, b] = await Promise.all(frames.map(async data => {
      const image = new Image()
      image.src = 'data:image/png;base64,' + data
      await image.decode()
      const canvas = document.createElement('canvas')
      canvas.width = image.width
      canvas.height = image.height
      const ctx = canvas.getContext('2d')
      ctx.drawImage(image, 0, 0)
      return ctx.getImageData(0, 0, image.width, image.height)
    }))
    let area = 0
    let rim = 0
    let beyondRim = 0
    let beyondFarRim = 0
    let brightEdge = 0
    const border = Math.min(a.width, a.height) * .035
    const cx = (Math.min(...contours[1].map(p => p.x)) + Math.max(...contours[1].map(p => p.x))) / 2 - sceneBox.x
    const ctx = document.createElement('canvas').getContext('2d')
    const [innerRim, outerRim, clearance] = contours.map(contour => {
      const path = new Path2D()
      path.moveTo(contour[0].x - sceneBox.x, contour[0].y - sceneBox.y)
      for (const { x, y } of contour.slice(1)) path.lineTo(x - sceneBox.x, y - sceneBox.y)
      path.closePath()
      return path
    })
    for (let i = 0; i < a.data.length; i += 4) {
      const delta = Math.max(Math.abs(a.data[i] - b.data[i]), Math.abs(a.data[i + 1] - b.data[i + 1]),
        Math.abs(a.data[i + 2] - b.data[i + 2]))
      if (delta < 12) continue
      area++
      const col = i / 4 % a.width
      const row = Math.floor(i / 4 / a.width)
      if (delta >= 48 && Math.min(col, row, a.width - 1 - col, a.height - 1 - row) < border) brightEdge++
      if (!ctx.isPointInPath(innerRim, col, row) && ctx.isPointInPath(outerRim, col, row)) rim++
      if (!ctx.isPointInPath(clearance, col, row)) {
        if (col < cx) beyondRim++
        else beyondFarRim++
      }
    }
    return { area, rim, beyondRim, beyondFarRim, brightEdge }
  }, {
    frames: [shown.toString('base64'), hidden.toString('base64')],
    contours, sceneBox,
  })
}

const transientLayers = '.kawoosh, .aperture-light, .return-wake'

async function assertTransientsHidden(page) {
  const visible = await page.locator(transientLayers).evaluateAll(layers => layers
    .filter(layer => layer.checkVisibility({ opacityProperty: true, visibilityProperty: true }))
    .map(layer => layer.className))
  assert.deepEqual(visible, [], 'Opening light, surge and wake have cleared')
}

async function assertSettledGate(page) {
  await assertTransientsHidden(page)
  assert.equal(await page.locator(horizon).evaluate(el => Number(getComputedStyle(el).opacity)), 1,
    'The membrane stays open')
  assert.ok(await page.locator(scene).evaluate(el => el.getAnimations({ subtree: true }).every(
    animation => animation.effect.getTiming().iterations === Infinity)), 'Only ambient motion may remain')
}

async function pauseOpening(gate) {
  const animations = await gate.evaluateHandle(el => {
    const items = el.getAnimations({ subtree: true })
    items.forEach(animation => animation.pause())
    return items
  })
  const { delay, duration, iterations } = await gate.locator('.kawoosh').evaluate(layer =>
    layer.getAnimations()[0].effect.getTiming())
  assert.equal(iterations, 1, 'Opening plays once')
  async function seek(time) {
    await animations.evaluate((items, time) => items.forEach(animation => { animation.currentTime = time }), time)
  }
  return { delay, duration, seek }
}

test('rim charge precedes a breach, projecting crest and retracting wake', async t => {
  const page = await openGate(t, unknown, { viewport: { width: 1440, height: 900 }, reducedMotion: 'no-preference' })
  const gate = page.locator(scene)
  const { delay, duration, seek } = await pauseOpening(gate)
  const clip = await checkAssembledRing(page)
  const framePosition = () => gate.locator('.wave-frames').evaluate(el => {
    const style = getComputedStyle(el)
    return [style.translate, style.transform]
  })
  const firstChargedModule = () => gate.locator('.charge-arc').evaluateAll(items =>
    items.findIndex(el => Number(getComputedStyle(el).opacity) > .25))
  await seek(delay * .5)
  const earlyModule = await firstChargedModule()
  await seek(delay * .8)
  assert.ok(earlyModule >= 0 && await firstChargedModule() > earlyModule, 'The charge moves around the rim')
  assert.ok(await gate.locator('.kawoosh').evaluate(el => !el.checkVisibility({ visibilityProperty: true })),
    'No water projects during charge')
  const dark = await apertureBrightness(page, clip)
  assert.equal(await gate.locator(horizon).evaluate(el => Number(getComputedStyle(el).opacity)), 0)

  await seek(delay + duration * .13)
  assert.ok(await apertureBrightness(page, clip) > dark + 8, 'Water breaks through inside the charged rim')
  const breach = await paintedFootprint(gate, '.kawoosh')
  const breachFrame = await framePosition()
  await seek(delay + duration * .43)
  const crest = await paintedFootprint(gate, '.kawoosh')
  const crestFrame = await framePosition()
  assert.notDeepEqual(crestFrame, breachFrame, 'The water silhouette changes as it advances')
  const light = await paintedFootprint(gate, '.aperture-light')
  assert.ok(crest.area > breach.area * 1.1 &&
    crest.beyondRim > Math.max(100, breach.beyondRim * 2, crest.beyondFarRim * 2),
    'The painted wave expands and projects beyond the foreground rim: ' + JSON.stringify({ breach, crest }))
  assert.ok(light.rim > 100, 'The flash reaches the rim: ' + JSON.stringify(light))
  await seek(delay + duration * .84)
  const retreat = await paintedFootprint(gate, '.kawoosh')
  assert.notDeepEqual(await framePosition(), crestFrame, 'The return uses another water shape')
  // The returning water still covers the aperture. Measure contraction at the
  // physical rim and outside it, where the crest projected in front of the gate.
  assert.ok(retreat.rim < crest.rim * .5 && retreat.beyondRim < crest.beyondRim * .5,
    'The crest draws back into the aperture: ' + JSON.stringify({ crest, retreat }))
  assert.ok(await gate.locator('.return-wake').evaluate(el => el.checkVisibility({ opacityProperty: true, visibilityProperty: true })),
    'Retraction disturbs the underlying membrane')
  await seek(delay + duration + 1000)
  await assertTransientsHidden(page)
  assert.ok(await apertureBrightness(page, clip) > dark + 24, 'The settled water remains illuminated')
})

test('320px entrance keeps the projecting crest clear of the scene edges', async t => {
  const page = await openGate(t, unknown, { viewport: { width: 320, height: 568 }, reducedMotion: 'no-preference' })
  const gate = page.locator(scene)
  const { delay, duration, seek } = await pauseOpening(gate)
  for (const fraction of [.40, .43, .47]) {
    await seek(delay + duration * fraction)
    const crest = await paintedFootprint(gate, '.kawoosh')
    assert.ok(crest.beyondRim > 100, 'The crest still projects past the physical rim on mobile')
    assert.ok(crest.brightEdge < crest.area * .002,
      `Only scattered spray may reach the edge at ${fraction} of the flight: ${JSON.stringify(crest)}`)
  }
})

for (const [width, height] of [[1440, 900], [320, 568]]) {
  test(`${width}×${height} shows the entire oblique ring around the open membrane under reduced motion`, async t => {
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
    await assertSettledGate(page)
  }
})

test('entry with reduced motion stays open as live preferences change', async t => {
  const page = await openGate(t, unknown, { reducedMotion: 'reduce' })
  const gate = page.locator(scene)
  for (const preference of ['reduce', 'no-preference', 'reduce', 'no-preference']) {
    await page.emulateMedia({ reducedMotion: preference })
    const reduced = preference === 'reduce'
    await page.waitForFunction(({ scene, reduced }) => {
      const animations = document.querySelector(scene).getAnimations({ subtree: true })
      return reduced ? !animations.length : animations.some(animation => animation.playState === 'running')
    }, { scene, reduced })
    await assertSettledGate(page)
    if (reduced) {
      const clip = await checkAssembledRing(page)
      assert.ok(await gate.locator(horizon).evaluate(el =>
        el.checkVisibility({ opacityProperty: true, visibilityProperty: true }) && Number(getComputedStyle(el).opacity) >= .95))
      const lit = await apertureBrightness(page, clip)
      assert.ok(lit > 45, `Reduced motion should show the lit surface immediately (observed ${lit})`)
    }
  }
})

for (const action of ['reduce motion', 'navigate Home']) {
  test(`interrupt the opening wave mid-flight to ${action}`, async t => {
    const page = await openGate(t, unknown, { reducedMotion: 'no-preference' })
    const gate = page.locator(scene)
    await page.waitForFunction(() => {
      const wave = document.querySelector('.kawoosh')
      const flight = wave.getAnimations()[0]
      if (!flight || !wave.checkVisibility({ opacityProperty: true, visibilityProperty: true })) return false
      const { delay, duration } = flight.effect.getTiming()
      return flight.currentTime >= delay + duration * .35
    })
    const animations = await gate.evaluateHandle(el => el.getAnimations({ subtree: true }))
    if (action === 'navigate Home') {
      await page.getByRole('link', { name: 'Back to home' }).click()
      await page.waitForURL(base.href)
      await gate.waitFor({ state: 'detached' })
    }
    else {
      await page.emulateMedia({ reducedMotion: 'reduce' })
      await page.waitForFunction(selector => !document.querySelector(selector).getAnimations({ subtree: true }).length, scene)
      await assertSettledGate(page)
      await page.emulateMedia({ reducedMotion: 'no-preference' })
      await page.waitForFunction(selector => document.querySelector(selector).getAnimations({ subtree: true }).length > 0, scene)
      await assertSettledGate(page)
    }
    assert.ok(await animations.evaluate(items => items.length > 0 && items.every(animation =>
      animation.playState !== 'running' && !document.getAnimations().includes(animation))),
    'The original opening animations are retired')
  })
}
