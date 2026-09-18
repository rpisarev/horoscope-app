import { flushPromises, shallowMount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const routing = vi.hoisted(() => ({
  params: {} as Record<string, string>,
  replace: vi.fn().mockResolvedValue(undefined),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: routing.params }),
  useRouter: () => ({ replace: routing.replace }),
  RouterLink: { template: '<a><slot /></a>' },
}))

beforeEach(() => {
  vi.resetModules()
  vi.clearAllMocks()
  routing.params = { sign: 'aries', year: '2026', month: '07', day: '16' }
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

function response(status: number, payload: unknown) {
  return { ok: status === 200, status, headers: new Headers({ 'content-type': 'application/json' }), json: async () => payload }
}

const views = [
  ['HoroscopeView', () => import('../../src/views/HoroscopeView.vue')],
  ['ArchiveForecast', () => import('../../src/views/ArchiveForecast.vue')],
] as const

describe.each(views)('%s forecast read', (name, loadView) => {
  it.each([
    [200, { text: 'Published forecast text' }, 'Published forecast text'],
    [404, { error: 'forecast_not_published', message: 'Forecast is not published' }, 'Прогноз ещё не опубликован'],
    [500, { error: 'failure' }, 'Не удалось загрузить прогноз'],
  ])('renders status %s with no metadata or generated substitute', async (status, payload, expected) => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    routing.params.day = name === 'HoroscopeView' ? '2026-07-16' : '16'
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/years') return response(200, [2026])
      if (url === '/api/forecast?sign=aries&date=2026-07-16') return response(Number(status), payload)
      throw new Error(`Unexpected request: ${url}`)
    }))
    const { default: component } = await loadView()
    const wrapper = shallowMount(component, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    expect(wrapper.text()).toContain(expected)
    expect(fetch).toHaveBeenCalledWith('/api/forecast?sign=aries&date=2026-07-16')
    expect(vi.mocked(fetch).mock.calls.every(([url]) => url !== '/api/meta')).toBe(true)
    wrapper.unmount()
  })
})

describe('explicit archive and invalid routes without metadata', () => {
  it('renders the archive month before metadata and enables the existing date controls after it loads', async () => {
    const { default: ArchiveMonth } = await import('../../src/views/ArchiveMonth.vue')
    const { refreshBusinessDate } = await import('../../src/utils/businessDate')
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/meta') return response(200, { business_date: '2026-07-16', timezone: 'Europe/Kyiv' })
      return response(200, [2026])
    }))
    const wrapper = shallowMount(ArchiveMonth, { global: { stubs: {
      RouterLink: { props: ['to'], template: '<a :data-route-name="to.name"><slot /></a>' },
    } } })
    await flushPromises()
    expect(wrapper.text()).toContain('Архив гороскопов')
    expect(wrapper.text()).toContain('Июль 2026')
    expect(wrapper.text()).toContain('Текущая дата недоступна')
    expect(wrapper.findAll('a[data-route-name="archive-forecast"]')).toHaveLength(0)
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledWith('/api/years')
    await refreshBusinessDate()
    await flushPromises()
    expect(wrapper.findAll('a[data-route-name="archive-forecast"]')).toHaveLength(15)
    expect(wrapper.find('a[data-route-name="horoscope"]').text()).toContain('Открыть прогноз на сегодня')
    expect(wrapper.text()).not.toContain('Текущая дата недоступна')
    wrapper.unmount()
  })

  it.each(['HoroscopeView', 'ArchiveMonth'])('renders contextual NotFound in %s without guessing a date', async name => {
    routing.params = { sign: 'invalid', year: 'invalid', month: 'invalid', day: 'invalid' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(200, [])))
    const { default: component } = name === 'HoroscopeView'
      ? await import('../../src/views/HoroscopeView.vue')
      : await import('../../src/views/ArchiveMonth.vue')
    const wrapper = shallowMount(component, { global: { stubs: {
      NotFound: { props: ['title'], template: '<p data-testid="not-found">{{ title }}</p>' },
      RouterLink: true,
    } } })
    await flushPromises()
    expect(wrapper.find('[data-testid="not-found"]').exists()).toBe(true)
    expect(vi.mocked(fetch).mock.calls.every(([url]) => url === '/api/years')).toBe(true)
    wrapper.unmount()
  })

  it('waits only for the existing invalid archive-date fallback, then keeps that explicit date on refresh', async () => {
    routing.params.year = 'invalid'
    const { default: ArchiveForecast } = await import('../../src/views/ArchiveForecast.vue')
    const { refreshBusinessDate } = await import('../../src/utils/businessDate')
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/meta') return response(200, { business_date: '2026-07-16', timezone: 'Europe/Kyiv' })
      if (url === '/api/years') return response(200, [2026])
      return response(200, { text: 'Published forecast text' })
    }))
    const wrapper = shallowMount(ArchiveForecast, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    expect(wrapper.find('[role="status"]').text()).toBe('Загрузка…')
    expect(vi.mocked(fetch).mock.calls.every(([url]) => url === '/api/years')).toBe(true)
    await refreshBusinessDate()
    await flushPromises()
    expect(wrapper.text()).toContain('Published forecast text')
    expect(routing.replace).toHaveBeenCalledWith({ name: 'archive-forecast', params: { sign: 'aries', year: '2026', month: '07', day: '16' } })
    const forecastCalls = () => vi.mocked(fetch).mock.calls.filter(([url]) => String(url).startsWith('/api/forecast'))
    expect(forecastCalls()).toHaveLength(1)
    await refreshBusinessDate()
    await flushPromises()
    expect(forecastCalls()).toHaveLength(1)
    wrapper.unmount()
  })
})
