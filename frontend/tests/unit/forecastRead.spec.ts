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
  ])('renders status %s without generating a substitute', async (status, payload, expected) => {
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
    wrapper.unmount()
  })
})
