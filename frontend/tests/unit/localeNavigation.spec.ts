import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Router } from 'vue-router'

vi.mock('../../src/views/Home.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../../src/views/HoroscopeView.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../../src/views/ArchiveMonth.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../../src/views/ArchiveForecast.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../../src/views/NotFound.vue', () => ({ default: { template: '<div />' } }))

let router: Router
let language: typeof import('../../src/utils/locale')

beforeEach(async () => {
  vi.resetModules()
  window.history.replaceState({}, '', '/')
  vi.stubGlobal('scrollTo', vi.fn())
  vi.stubGlobal('fetch', vi.fn())
  router = (await import('../../src/router/index')).default
  language = await import('../../src/utils/locale')
})

afterEach(() => {
  router.options.history.destroy()
  vi.unstubAllGlobals()
})

describe('URL language', () => {
  it.each(['en', 'EN', 'fr', 'UK', '', 'uk&lang=uk', 'uk&lang=ru'])(
    'canonicalizes lang=%s before committing the navigation', async value => {
      await router.push('/')
      const previousLength = window.history.length
      const path = '/horoscope/aries/2026-11-21'
      await router.push(`${path}?ref=a&lang=${value}&ref=b#details`)
      const expected = `${path}?ref=a&ref=b#details`
      expect(router.currentRoute.value.fullPath).toBe(expected)
      expect(window.history.length).toBe(previousLength + 1)
      expect(window.history.state).toMatchObject({ back: '/', current: expected })
      expect(fetch).not.toHaveBeenCalled()
    },
  )

  it('replaces the initial entry for a cold link with a bare language key', async () => {
    router.options.history.destroy()
    window.history.replaceState(null, '', '/archive/aries/2026/11?lang&from=mail#day')
    vi.resetModules()
    router = (await import('../../src/router/index')).default
    const length = window.history.length
    const wrapper = mount({ template: '<RouterView />' }, { global: { plugins: [router] } })
    try {
      await router.isReady()
      expect(router.currentRoute.value.fullPath).toBe('/archive/aries/2026/11?from=mail#day')
      expect(window.location.search).toBe('?from=mail')
      expect(window.history.length).toBe(length)
      expect(fetch).not.toHaveBeenCalled()
    } finally {
      wrapper.unmount()
    }
  })

  it('preserves the requested language, path and Back entry on a blocked initial redirect', async () => {
    router.options.history.destroy()
    window.history.replaceState(null, '', '/archive?source=mail&lang=uk&ref=1&ref=2#calendar')
    vi.resetModules()
    router = (await import('../../src/router/index')).default
    language = await import('../../src/utils/locale')
    const businessDate = await import('../../src/utils/businessDate')
    let rejectMeta: (reason: Error) => void
    vi.mocked(fetch).mockReturnValueOnce(new Promise((_, reject) => { rejectMeta = reject }))
    let selection: ReturnType<typeof language.useLocale>
    const wrapper = mount(defineComponent({
      setup() {
        selection = language.useLocale()
        // The application also requests the business date when its shell mounts.
        void businessDate.refreshBusinessDate().catch(() => {})
        return () => selection.locale.value
      },
    }), { global: { plugins: [router] } })
    try {
      await flushPromises()
      expect(wrapper.text()).toBe('uk')
      expect(fetch).toHaveBeenCalledTimes(1)
      rejectMeta(new Error('offline'))
      await flushPromises()
      expect(businessDate.businessDateError.value).not.toBe('')
      expect(router.currentRoute.value.matched).toHaveLength(0)
      expect(wrapper.text()).toBe('uk')

      const origin = window.location.origin
      const assign = vi.fn()
      const replace = vi.fn()
      const realWindow = window
      // JSDOM does not implement navigation between documents.
      vi.stubGlobal('window', { location: { origin, assign, replace } })
      try {
        await selection.switchLocale('uk')
        expect(assign).not.toHaveBeenCalled()
        await selection.switchLocale('ru')
        expect(assign).toHaveBeenCalledExactlyOnceWith(`${origin}/archive?source=mail&ref=1&ref=2&lang=ru#calendar`)
        expect(replace).not.toHaveBeenCalled()
      } finally {
        vi.stubGlobal('window', realWindow)
      }
      expect(fetch).toHaveBeenCalledTimes(1)
    } finally {
      wrapper.unmount()
    }
  })

  it.each([
    ['/horoscope?lang=ru&ref=x#day', '/horoscope/capricorn/2026-11-22?lang=ru&ref=x#day'],
    ['/archive?lang=uk#month', '/archive/capricorn/2026/11?lang=uk#month'],
    ['/archive?lang=bad&ref=x', '/archive/capricorn/2026/11?ref=x'],
  ])('retains the resolved language for %s', async (path, expected) => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({
      business_date: '2026-11-22', timezone: 'Europe/Kyiv',
    })))
    await router.push(path)
    expect(router.currentRoute.value.fullPath).toBe(expected)
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('switches on the current path and restores the selected language with Back/Forward', async () => {
    const path = '/unknown/route'
    await router.push(`${path}?from=a#details`)
    let selection: ReturnType<typeof language.useLocale>
    const wrapper = mount(defineComponent({
      setup() {
        selection = language.useLocale()
        return () => selection.locale.value
      },
    }), { global: { plugins: [router] } })
    try {
      expect(wrapper.text()).toBe('en')
      await selection.switchLocale('uk')
      expect(router.currentRoute.value.fullPath).toBe(`${path}?from=a&lang=uk#details`)
      expect(wrapper.text()).toBe('uk')
      await selection.switchLocale('ru')
      expect(wrapper.text()).toBe('ru')
      await selection.switchLocale('en')
      expect(router.currentRoute.value.fullPath).toBe(`${path}?from=a#details`)
      expect(wrapper.text()).toBe('en')
      router.back()
      await vi.waitFor(() => expect(wrapper.text()).toBe('ru'))
      router.back()
      await vi.waitFor(() => expect(wrapper.text()).toBe('uk'))
      router.forward()
      await vi.waitFor(() => expect(wrapper.text()).toBe('ru'))
      expect(router.currentRoute.value.fullPath).toBe(`${path}?from=a&lang=ru#details`)
      expect(fetch).not.toHaveBeenCalled()
    } finally {
      wrapper.unmount()
    }
  })

  it('uses English without a router provider', () => {
    const wrapper = mount(defineComponent({
      setup() {
        const { locale } = language.useLocale()
        return () => locale.value
      },
    }))
    expect(wrapper.text()).toBe('en')
    wrapper.unmount()
  })
})
