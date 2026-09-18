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
  routing.params = { sign: 'aries', day: '2026-07-16' }
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

function response(status: number, payload: unknown) {
  return { ok: status === 200, status, headers: new Headers({ 'content-type': 'application/json' }), json: async () => payload }
}

describe('HoroscopeView forecast read', () => {
  it.each([
    [200, { text: 'Published forecast text' }, 'Published forecast text'],
    [404, { error: 'forecast_not_published', message: 'Forecast is not published' }, 'Прогноз ещё не опубликован'],
    [500, { error: 'failure' }, 'Не удалось загрузить прогноз'],
  ])('renders status %s with no metadata or generated substitute', async (status, payload, expected) => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url === '/api/forecast?sign=aries&date=2026-07-16') return response(Number(status), payload)
      throw new Error(`Unexpected request: ${url}`)
    }))
    const { default: component } = await import('../../src/views/HoroscopeView.vue')
    const wrapper = shallowMount(component, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    expect(wrapper.text()).toContain(expected)
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledWith('/api/forecast?sign=aries&date=2026-07-16')
    wrapper.unmount()
  })

  it('renders contextual NotFound without guessing a date', async () => {
    routing.params = { sign: 'invalid', day: 'invalid' }
    vi.stubGlobal('fetch', vi.fn())
    const { default: component } = await import('../../src/views/HoroscopeView.vue')
    const wrapper = shallowMount(component, { global: { stubs: {
      NotFound: { props: ['title'], template: '<p data-testid="not-found">{{ title }}</p>' },
      RouterLink: true,
    } } })
    await flushPromises()
    expect(wrapper.find('[data-testid="not-found"]').exists()).toBe(true)
    expect(fetch).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
