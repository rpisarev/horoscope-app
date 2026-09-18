import { flushPromises, shallowMount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

const { push } = vi.hoisted(() => ({ push: vi.fn() }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))
import Home from '../../src/views/Home.vue'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe('Home sign selection', () => {
  it('loads the authoritative date before navigating', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ business_date: '2026-07-16', timezone: 'Europe/Kyiv' }),
    }))
    const wrapper = shallowMount(Home)
    wrapper.findComponent({ name: 'ZodiacWheel' }).vm.$emit('select', { slug: 'aries' })
    await flushPromises()
    expect(push).toHaveBeenCalledWith({
      name: 'horoscope', params: { sign: 'aries', day: '2026-07-16' },
    })
    wrapper.unmount()
  })

  it('stays on Home if the server date cannot be loaded', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    const wrapper = shallowMount(Home)
    wrapper.findComponent({ name: 'ZodiacWheel' }).vm.$emit('select', { slug: 'aries' })
    await flushPromises()
    expect(push).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
