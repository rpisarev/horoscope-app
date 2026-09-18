import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Router } from 'vue-router'

vi.mock('../../src/views/Home.vue', () => ({ default: { template: '<div>Home</div>' } }))
vi.mock('../../src/views/HoroscopeView.vue', () => ({ default: { template: '<div data-testid="forecast">Forecast</div>' } }))

let router: Router
let wrapper: ReturnType<typeof mount> | undefined
let monthResponse: (url: URL) => unknown
let yearsResponse: (url: URL) => unknown
let businessDate: typeof import('../../src/utils/businessDate')

const response = (payload: unknown, status = 200) => ({ ok: status === 200, status, json: async () => payload })
function monthData(url: URL, published: number[] = []) {
  const year = Number(url.searchParams.get('year'))
  const month = Number(url.searchParams.get('month'))
  return { year, month, locale: 'ru', forecast_type: 'daily', expected_sign_count: 13,
    days: Array.from({ length: new Date(Date.UTC(year, month, 0)).getUTCDate() }, (_, index) => ({
      date: `${year}-${String(month).padStart(2, '0')}-${String(index + 1).padStart(2, '0')}`,
      has_forecast: published.includes(index + 1),
      forecast_count: 1, missing_count: 12, has_full_coverage: false,
    })),
  }
}
function deferred() {
  let resolve!: (value: unknown) => void
  let reject!: (reason: Error) => void
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
function requests(path: string) {
  return vi.mocked(fetch).mock.calls.map(([url]) => new URL(String(url), 'http://localhost')).filter(url => url.pathname === path)
}
function calendarLinks() {
  return wrapper!.get('[aria-label="Календарь архива"]').findAll('a')
}
function calendarHrefs() {
  return calendarLinks().map(link => link.attributes('href'))
}
async function openMonth(path = '/archive/aries/2026/09') {
  await router.push(path)
  wrapper = mount({ template: '<RouterView />' }, { global: {
    plugins: [router],
    stubs: { ZodiacCarousel: true, YearSwiper: true, MonthSwiper: true, CosmicGate404: { template: '<div><slot /></div>' } },
  } })
  await flushPromises()
}

beforeEach(async () => {
  vi.resetModules()
  vi.clearAllMocks()
  window.history.replaceState({}, '', '/')
  vi.stubGlobal('scrollTo', vi.fn())
  monthResponse = url => response(monthData(url))
  yearsResponse = () => response([2025, 2026, 2027])
  vi.stubGlobal('fetch', vi.fn((input: string) => {
    const url = new URL(input, 'http://localhost')
    if (url.pathname === '/api/years') return yearsResponse(url)
    if (url.pathname === '/api/archive/month') return monthResponse(url)
    if (url.pathname === '/api/meta') return response({ business_date: '2026-09-18', timezone: 'Europe/Kyiv' })
    throw new Error(`Unexpected request: ${input}`)
  }))
  router = (await import('../../src/router/index')).default
  businessDate = await import('../../src/utils/businessDate')
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  router.options.history.destroy()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('published archive availability', () => {
  it('makes only published selected-sign days clickable, including past, today, and future', async () => {
    monthResponse = url => response(monthData(url, [17, 18, 19]))
    await businessDate.refreshBusinessDate()
    await openMonth()
    expect(calendarHrefs()).toEqual([
      '/horoscope/aries/2026-09-17', '/horoscope/aries/2026-09-18', '/horoscope/aries/2026-09-19',
    ])
    expect(calendarHrefs()).not.toContain('/horoscope/aries/2026-09-16')
    expect(calendarLinks()[1].attributes('aria-current')).toBe('date')
    expect(requests('/api/archive/month')).toHaveLength(1)
    expect(Object.fromEntries(requests('/api/archive/month')[0].searchParams)).toEqual({
      year: '2026', month: '9', sign: 'aries', locale: 'ru', type: 'daily',
    })
    expect(Object.fromEntries(requests('/api/years')[0].searchParams)).toEqual({ sign: 'aries', locale: 'ru', type: 'daily' })
    expect(requests('/api/archive/day')).toHaveLength(0)
  })

  it('disables every unpublished day, regardless of position or aggregate coverage', async () => {
    await businessDate.refreshBusinessDate()
    await openMonth()
    expect(calendarLinks()).toHaveLength(0)
    expect(wrapper!.text()).not.toContain('Доступны только прошедшие дни')
  })

  it('keeps unknown availability disabled while the month request is pending', async () => {
    const pending = deferred()
    let query!: URL
    monthResponse = url => { query = url; return pending.promise }
    await businessDate.refreshBusinessDate()
    await openMonth()
    expect(calendarLinks()).toHaveLength(0)
    expect(wrapper!.get('[role="status"]').text()).toContain('Загрузка доступных прогнозов')
    pending.resolve(response(monthData(query, [17])))
    await flushPromises()
    expect(calendarHrefs()).toEqual(['/horoscope/aries/2026-09-17'])
  })

  it.each([400, 500])('keeps days disabled after HTTP %s, with no past-date fallback', async status => {
    monthResponse = () => response({}, status)
    await businessDate.refreshBusinessDate()
    await openMonth()
    expect(calendarLinks()).toHaveLength(0)
    expect(wrapper!.get('[role="alert"]').text()).toContain('Не удалось загрузить доступные прогнозы')
  })

  it('treats a network failure as unavailable, without guessing past-day coverage', async () => {
    monthResponse = () => Promise.reject(new Error('offline'))
    await businessDate.refreshBusinessDate()
    await openMonth()
    expect(calendarLinks()).toHaveLength(0)
    expect(wrapper!.find('[role="alert"]').exists()).toBe(true)
  })

  it('loads availability even if business metadata is unavailable', async () => {
    vi.mocked(fetch).mockImplementationOnce(() => Promise.reject(new Error('meta unavailable')))
    await expect(businessDate.refreshBusinessDate()).rejects.toThrow('meta unavailable')
    monthResponse = url => response(monthData(url, [19]))
    await openMonth()
    expect(businessDate.todayIso()).toBeNull()
    expect(calendarHrefs()).toEqual(['/horoscope/aries/2026-09-19'])
    expect(wrapper!.text()).not.toContain('Открыть прогноз на сегодня')
    expect(requests('/api/meta')).toHaveLength(1) // Only the explicit initial metadata attempt.
  })

  it('refetches one month per sign/year/month route change, and years only per sign', async () => {
    await openMonth()
    for (const path of ['/archive/taurus/2026/09', '/archive/taurus/2027/09', '/archive/taurus/2027/10']) {
      await router.push(path)
      await flushPromises()
    }
    expect(requests('/api/archive/month').map(url => Object.fromEntries(url.searchParams))).toEqual([
      { sign: 'aries', year: '2026', month: '9', locale: 'ru', type: 'daily' },
      { sign: 'taurus', year: '2026', month: '9', locale: 'ru', type: 'daily' },
      { sign: 'taurus', year: '2027', month: '9', locale: 'ru', type: 'daily' },
      { sign: 'taurus', year: '2027', month: '10', locale: 'ru', type: 'daily' },
    ])
    expect(requests('/api/years').map(url => url.searchParams.get('sign'))).toEqual(['aries', 'taurus'])
    expect(requests('/api/meta')).toHaveLength(0)
    expect(fetch).toHaveBeenCalledTimes(6)
  })

  it('does not duplicate the month request when padding the existing month URL', async () => {
    await openMonth('/archive/aries/2026/9')
    expect(router.currentRoute.value.path).toBe('/archive/aries/2026/09')
    expect(requests('/api/archive/month')).toHaveLength(1)
  })

  it('clears previous-sign availability while the next sign is loading', async () => {
    const pending = deferred()
    let nextQuery!: URL
    monthResponse = url => {
      if (url.searchParams.get('sign') === 'aries') return response(monthData(url, [17]))
      nextQuery = url
      return pending.promise
    }
    await openMonth()
    expect(calendarHrefs()).toEqual(['/horoscope/aries/2026-09-17'])
    await router.push('/archive/taurus/2026/09')
    await flushPromises()
    expect(calendarLinks()).toHaveLength(0)
    pending.resolve(response(monthData(nextQuery, [18])))
    await flushPromises()
    expect(calendarHrefs()).toEqual(['/horoscope/taurus/2026-09-18'])
  })

  it.each(['success', 'failure'])('ignores a stale older month response (%s)', async outcome => {
    const old = deferred()
    let oldQuery!: URL
    monthResponse = url => {
      if (url.searchParams.get('sign') === 'aries') { oldQuery = url; return old.promise }
      return response(monthData(url, [18]))
    }
    await openMonth()
    await router.push('/archive/taurus/2026/09')
    await flushPromises()
    expect(calendarHrefs()).toEqual(['/horoscope/taurus/2026-09-18'])
    if (outcome === 'success') old.resolve(response(monthData(oldQuery, [17])))
    else old.reject(new Error('old request failed'))
    await flushPromises()
    expect(calendarHrefs()).toEqual(['/horoscope/taurus/2026-09-18'])
    expect(wrapper!.find('[role="alert"]').exists()).toBe(false)
  })

  it('ignores an older sign year list instead of rejecting the current route', async () => {
    const oldYears = deferred()
    yearsResponse = url => url.searchParams.get('sign') === 'aries' ? oldYears.promise : response([2026])
    monthResponse = url => response(monthData(url, [18]))
    await openMonth()
    await router.push('/archive/taurus/2026/09')
    await flushPromises()
    oldYears.resolve(response([2025]))
    await flushPromises()
    expect(calendarHrefs()).toEqual(['/horoscope/taurus/2026-09-18'])
    expect(wrapper!.text()).not.toContain('Архив за этот год недоступен')
  })

  it('navigates an available day directly to the canonical forecast page', async () => {
    monthResponse = url => response(monthData(url, [18]))
    await openMonth()
    const link = calendarLinks()[0]
    expect(link.attributes('href')).toBe('/horoscope/aries/2026-09-18')
    await link.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/horoscope/aries/2026-09-18')
    expect(wrapper!.find('[data-testid="forecast"]').exists()).toBe(true)
    expect(requests('/api/archive/month')).toHaveLength(1)
    expect(requests('/api/archive/day')).toHaveLength(0)
  })

  it('keeps contextual 404 for malformed month routes without making archive requests', async () => {
    await openMonth('/archive/not-a-sign/2026/09')
    expect(wrapper!.text()).toContain('Такой знак не найден')
    expect(fetch).not.toHaveBeenCalled()
  })
})
