import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Router } from 'vue-router'

vi.mock('../../src/views/Home.vue', () => ({ default: { template: '<div>Home</div>' } }))
vi.mock('../../src/views/ArchiveMonth.vue', () => ({ default: { template: '<div>Archive month</div>' } }))

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

const validPath = '/horoscope/aries/2026-07-16'
const loading = '— прогноз загружается —'
const unpublished = 'Прогноз ещё не опубликован'
const loadError = 'Не удалось загрузить прогноз'
const invalidRoutes = [
  ['/horoscope/unknown/2026-07-16', 'Такой знак не найден'],
  ['/horoscope/Aries/2026-07-16', 'Такой знак не найден'],
  ['/horoscope/aries/not-a-date', 'Такой день не найден'],
  ['/horoscope/aries/2026-7-16', 'Такой день не найден'],
  ['/horoscope/aries/2026-02-29', 'Такой день не найден'],
  ['/horoscope/aries/2026-04-31', 'Такой день не найден'],
  ['/horoscope/aries/2026-13-01', 'Такой день не найден'],
  ['/horoscope/aries/2026-07-00', 'Такой день не найден'],
]

let router: Router
let wrapper: ReturnType<typeof mount> | undefined
let HoroscopeView: typeof import('../../src/views/HoroscopeView.vue')['default']
let requests: Array<{ url: string; response: ReturnType<typeof deferred<Response>> }>
let replace: ReturnType<typeof vi.spyOn>
let consoleError: ReturnType<typeof vi.spyOn>

beforeEach(async () => {
  vi.resetModules()
  window.history.replaceState({}, '', '/')
  vi.stubGlobal('scrollTo', vi.fn())
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  requests = []
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    // No metadata, providers, or network calls: every forecast is explicitly settled by the test.
    expect(url).toMatch(/^\/api\/forecast\?sign=[a-z]+&date=\d{4}-\d{2}-\d{2}$/)
    const response = deferred<Response>()
    requests.push({ url, response })
    return response.promise
  }))
  router = (await import('../../src/router/index')).default
  HoroscopeView = (await import('../../src/views/HoroscopeView.vue')).default
  replace = vi.spyOn(router, 'replace')
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  router.options.history.destroy()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

async function navigate(path: string) {
  await router.push(path)
  await flushPromises()
}

async function mountRoute(path = validPath) {
  await navigate(path)
  wrapper = mount({ template: '<RouterView />' }, { global: {
    plugins: [router],
    stubs: {
      ZodiacCarousel: true,
      DaySlider: true,
      CosmicGate404: { template: '<div><slot /></div>' },
    },
  } })
  await flushPromises()
  return wrapper
}

async function respond(index: number, text: string, status = 200) {
  const body = status === 404 ? { error: 'forecast_not_published' } : { text }
  requests[index].response.resolve(new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  }))
  await flushPromises()
}

async function settleStale(index: number, outcome: string) {
  if (outcome === 'reject') {
    requests[index].response.reject(new Error('stale request failed'))
    await flushPromises()
  } else {
    await respond(index, 'Stale forecast', outcome === '404' ? 404 : 200)
  }
}

function forecastSnapshot(page: ReturnType<typeof mount>) {
  // A hidden or detached DOM alone cannot detect late state writes.
  const state = page.getComponent(HoroscopeView).vm as unknown as {
    forecastText: string; errorText: string; isLoading: boolean
  }
  return () => ({ text: state.forecastText, error: state.errorText, loading: state.isLoading })
}

describe('HoroscopeView route recovery', () => {
  it.each(invalidRoutes)('recovers valid → %s → the same valid route without remounting', async (path, message) => {
    const page = await mountRoute()
    const viewId = page.getComponent(HoroscopeView).vm.$.uid
    await respond(0, 'Original forecast')
    expect(page.text()).toContain('Original forecast')

    await navigate(path)
    expect(page.text()).toContain(message)
    expect(page.find('article').exists()).toBe(false)
    expect(router.currentRoute.value.fullPath).toBe(path)
    expect(requests).toHaveLength(1)

    await navigate(validPath)
    expect(page.getComponent(HoroscopeView).vm.$.uid).toBe(viewId)
    expect(requests.map(request => request.url)).toEqual([
      '/api/forecast?sign=aries&date=2026-07-16',
      '/api/forecast?sign=aries&date=2026-07-16',
    ])
    expect(page.text()).toContain(loading)
    expect(page.text()).not.toContain('Original forecast')
    await respond(1, 'Reloaded forecast')
    expect(page.text()).toContain('Reloaded forecast')
    expect(replace).not.toHaveBeenCalled()
  })

  it.each(invalidRoutes)('does not fetch, replace or fall back on initial invalid route %s', async (path, message) => {
    const page = await mountRoute(path)
    expect(page.text()).toContain(message)
    expect(router.currentRoute.value.fullPath).toBe(path)
    expect(requests).toHaveLength(0)
    expect(replace).not.toHaveBeenCalled()

    await navigate('/horoscope/taurus/2024-02-29')
    expect(requests).toHaveLength(1)
    expect(requests[0].url).toBe('/api/forecast?sign=taurus&date=2024-02-29')
    await respond(0, 'Valid leap-day forecast')
    expect(page.text()).toContain('Valid leap-day forecast')
  })

  it.each(['success', 'reject', '404'])('ignores stale %s while invalid and reloads on return', async outcome => {
    const page = await mountRoute()
    const snapshot = forecastSnapshot(page)
    await navigate('/horoscope/aries/2026-02-30')
    expect(snapshot()).toEqual({ text: '', error: '', loading: false })
    await settleStale(0, outcome)
    expect(snapshot()).toEqual({ text: '', error: '', loading: false })
    expect(page.text()).toContain('Такой день не найден')
    expect(consoleError).not.toHaveBeenCalled()

    await navigate(validPath)
    expect(requests).toHaveLength(2)
    expect(page.text()).toContain(loading)
    await respond(1, 'Current forecast')
    expect(page.text()).toContain('Current forecast')
    expect(page.text()).not.toContain('Stale forecast')
  })

  it.each(['success', 'reject', '404'])('stale %s cannot end the restored route loading state', async outcome => {
    const page = await mountRoute()
    await navigate('/horoscope/unknown/2026-07-16')
    await navigate(validPath)
    expect(requests).toHaveLength(2)
    await settleStale(0, outcome)
    expect(page.text()).toContain(loading)
    expect(page.text()).not.toContain('Stale forecast')
    expect(consoleError).not.toHaveBeenCalled()
    await respond(1, 'Restored forecast')
    expect(page.text()).toContain('Restored forecast')
  })

  it.each(['success', 'reject', '404'])('stale %s cannot overwrite a completed restored forecast', async outcome => {
    const page = await mountRoute()
    await navigate('/horoscope/unknown/2026-07-16')
    await navigate(validPath)
    expect(requests).toHaveLength(2)
    await respond(1, 'Restored forecast')
    await settleStale(0, outcome)
    expect(page.text()).toContain('Restored forecast')
    expect(page.text()).not.toContain('Stale forecast')
    expect(page.text()).not.toContain(unpublished)
    expect(page.text()).not.toContain(loadError)
    expect(consoleError).not.toHaveBeenCalled()
  })

  it('keeps only the newest result across rapid sign/date changes', async () => {
    const page = await mountRoute()
    await navigate('/horoscope/taurus/2026-07-16')
    await navigate('/horoscope/gemini/2026-07-15')
    expect(requests.map(request => request.url)).toEqual([
      '/api/forecast?sign=aries&date=2026-07-16',
      '/api/forecast?sign=taurus&date=2026-07-16',
      '/api/forecast?sign=gemini&date=2026-07-15',
    ])
    await respond(2, 'Newest forecast')
    await respond(0, 'Older Aries forecast')
    await settleStale(1, 'reject')
    expect(page.text()).toContain('Newest forecast')
    expect(page.text()).not.toContain('Older Aries forecast')
    expect(consoleError).not.toHaveBeenCalled()
    expect(replace).not.toHaveBeenCalled()
  })

  it('does not fetch again or replace for repeated sign/day identity or query/hash changes', async () => {
    const page = await mountRoute()
    await navigate(validPath)
    await navigate(`${validPath}?from=calendar#forecast`)
    expect(requests).toHaveLength(1)
    await respond(0, 'Same forecast')
    await navigate(`${validPath}?from=calendar#forecast`)
    await navigate(validPath)
    expect(page.text()).toContain('Same forecast')
    expect(requests).toHaveLength(1)
    expect(replace).not.toHaveBeenCalled()
  })

  it('fetches once per committed control change without replace feedback', async () => {
    const page = await mountRoute()
    // Exercise the parent v-model boundary; Swiper behavior has separate ownership.
    const signControl = page.getComponent({ name: 'ZodiacCarousel' })
    const dayControl = page.getComponent({ name: 'DaySlider' })
    signControl.vm.$emit('update:modelValue', 'taurus')
    dayControl.vm.$emit('update:modelValue', '2026-07-15')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/horoscope/taurus/2026-07-15')
    expect(replace).toHaveBeenCalledTimes(1)
    expect(requests).toHaveLength(2)
    expect(requests[1].url).toBe('/api/forecast?sign=taurus&date=2026-07-15')
    signControl.vm.$emit('update:modelValue', 'taurus')
    dayControl.vm.$emit('update:modelValue', '2026-07-15')
    await flushPromises()
    expect(replace).toHaveBeenCalledTimes(1)
    expect(requests).toHaveLength(2)
    await respond(1, 'Selected forecast')
    expect(page.text()).toContain('Selected forecast')
  })

  it('does not fetch twice when an older control navigation finishes after its replacement', async () => {
    const page = await mountRoute()
    const delayedNavigation = deferred<void>()
    const guardStarted = deferred<void>()
    router.beforeEach(async to => {
      if (to.params.sign === 'taurus') {
        guardStarted.resolve()
        await delayedNavigation.promise
      }
    })
    const signControl = page.getComponent({ name: 'ZodiacCarousel' })
    signControl.vm.$emit('update:modelValue', 'taurus')
    await nextTick()
    await guardStarted.promise
    signControl.vm.$emit('update:modelValue', 'gemini')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/horoscope/gemini/2026-07-16')
    expect(requests).toHaveLength(2)
    await respond(1, 'Gemini forecast')
    delayedNavigation.resolve()
    await flushPromises()
    expect(requests).toHaveLength(2)
    expect(replace).toHaveBeenCalledTimes(2)
    expect(page.text()).toContain('Gemini forecast')
  })

  it.each([
    [404, unpublished],
    [500, loadError],
    [200, '— прогноз пока пуст —'],
  ])('preserves status %s after recovery', async (status, expected) => {
    const page = await mountRoute()
    await respond(0, 'Original forecast')
    await navigate('/horoscope/aries/2026-02-30')
    await navigate(validPath)
    expect(requests).toHaveLength(2)
    await respond(1, '', status)
    expect(page.text()).toContain(expected)
    expect(page.text()).not.toContain('Original forecast')
  })

  it('loads the legacy canonical replacement once and preserves its query/hash', async () => {
    const page = await mountRoute('/archive/aries/2026/7/16?from=calendar#forecast')
    expect(router.currentRoute.value.fullPath).toBe(`${validPath}?from=calendar#forecast`)
    expect(replace).toHaveBeenCalledTimes(1)
    expect(requests).toHaveLength(1)
    await respond(0, 'Canonical forecast')
    expect(page.text()).toContain('Canonical forecast')
  })

  it.each(['success', 'reject', '404'])('invalidates pending %s on unmount', async outcome => {
    const page = await mountRoute()
    const snapshot = forecastSnapshot(page)
    expect(snapshot().loading).toBe(true)
    await navigate('/')
    const retired = snapshot()
    await settleStale(0, outcome)
    expect(snapshot()).toEqual(retired)
    expect(consoleError).not.toHaveBeenCalled()
    expect(page.text()).toContain('Home')
    expect(requests).toHaveLength(1)
  })
})
