import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Router } from 'vue-router'

vi.mock('../../src/views/Home.vue', () => ({ default: { template: '<div>Home</div>' } }))
vi.mock('../../src/views/HoroscopeView.vue', () => ({ default: { template: '<div data-testid="forecast">Canonical forecast</div>' } }))
vi.mock('../../src/views/ArchiveMonth.vue', () => ({ default: { template: '<div>Archive month</div>' } }))

let router: Router
let wrapper: ReturnType<typeof mount>
beforeEach(async () => {
  vi.resetModules()
  vi.clearAllMocks()
  window.history.replaceState({}, '', '/')
  vi.stubGlobal('scrollTo', vi.fn())
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Metadata unavailable')))
  router = (await import('../../src/router/index')).default
  await router.push('/')
  wrapper = mount({ template: '<RouterView />' }, { global: {
    plugins: [router], stubs: { CosmicGate404: { template: '<div><slot /></div>' } },
  } })
  await flushPromises()
})
afterEach(() => {
  wrapper.unmount()
  router.options.history.destroy()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('legacy archive-day compatibility', () => {
  it.each([
    ['/archive/aries/2026/09/18', '/horoscope/aries/2026-09-18'],
    ['/archive/aries/2024/02/29', '/horoscope/aries/2024-02-29'],
    ['/archive/aries/2026/9/8', '/horoscope/aries/2026-09-08'],
    ['/archive/aries/2026/09/18?from=calendar#forecast', '/horoscope/aries/2026-09-18?from=calendar#forecast'],
  ])('replaces %s with %s without fetching metadata or forecasts', async (legacy, canonical) => {
    const replace = vi.spyOn(router, 'replace')
    const historyLength = window.history.length
    await router.push(legacy)
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe(canonical)
    expect(replace).toHaveBeenCalledTimes(1)
    expect(replace).toHaveBeenCalledWith(expect.objectContaining({ name: 'horoscope' }))
    expect(window.history.length).toBe(historyLength + 1)
    expect(window.history.state.back).toBe('/')
    expect(window.history.state.current).toBe(canonical)
    expect(wrapper.find('[data-testid="forecast"]').exists()).toBe(true)
    expect(fetch).not.toHaveBeenCalled()
  })

  it.each([
    ['/archive/not-a-sign/2026/09/18', 'Такой знак не найден'],
    ['/archive/aries/2026/02/30', 'Такой день не найден'],
    ['/archive/aries/2026/02/29', 'Такой день не найден'],
    ['/archive/aries/2026/13/01', 'Такой месяц не найден'],
    ['/archive/aries/2026/00/01', 'Такой месяц не найден'],
    ['/archive/aries/2026/09/0', 'Такой день не найден'],
    ['/archive/aries/2026/09/-1', 'Такой день не найден'],
    ['/archive/aries/2026/09/018', 'Такой день не найден'],
    ['/archive/aries/2026/09/18.0', 'Такой день не найден'],
    ['/archive/aries/bad-year/09/18', 'Архив за этот год недоступен'],
  ])('keeps invalid explicit route %s on contextual NotFound', async (path, message) => {
    const replace = vi.spyOn(router, 'replace')
    await router.push(path)
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe(path)
    expect(wrapper.text()).toContain(message)
    expect(wrapper.find('[data-testid="forecast"]').exists()).toBe(false)
    expect(replace).not.toHaveBeenCalled()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('validates parameter changes when the same compatibility component is reused', async () => {
    await router.push('/archive/aries/2026/02/30')
    await flushPromises()
    expect(wrapper.text()).toContain('Такой день не найден')
    await router.push('/archive/taurus/2026/09/18')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/horoscope/taurus/2026-09-18')
    expect(fetch).not.toHaveBeenCalled()
  })
})
