import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Router } from 'vue-router'

const meta = { business_date: '2026-11-22', timezone: 'Europe/Kyiv' }
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), {
  status,
  headers: { 'content-type': 'application/json' },
})

function pendingResponse() {
  let resolve!: (response: Response) => void
  const promise = new Promise<Response>(yes => { resolve = yes })
  return { promise, resolve }
}

let router: Router
let wrapper: ReturnType<typeof mount>
let read: (url: URL) => Response | Promise<Response>

async function open(path: string) {
  const { default: App } = await import('../../src/App.vue')
  await router.push(path)
  wrapper = mount(App, { global: {
    plugins: [router],
    stubs: {
      Starfield: true, ZodiacCarousel: true, YearSwiper: true, MonthSwiper: true,
      CosmicGate404: { template: '<div><slot /></div>' },
    },
  } })
  await flushPromises()
}

async function select(language: string) {
  await wrapper.get('#language-select').setValue(language)
  await flushPromises()
}

beforeEach(async () => {
  vi.resetModules()
  window.history.replaceState({}, '', '/')
  vi.stubGlobal('scrollTo', vi.fn())
  vi.stubGlobal('fetch', vi.fn((input: string) => {
    const url = new URL(input, 'http://localhost')
    return url.pathname === '/api/meta' ? json(meta) : read(url)
  }))
  router = (await import('../../src/router/index')).default
})

afterEach(() => {
  wrapper?.unmount()
  router.options.history.destroy()
  vi.unstubAllGlobals()
})

describe('localized product views', () => {
  it('updates Home, document language and focused Wheel details; a superseded sign response cannot replace the labels', async () => {
    const oldNames = pendingResponse()
    read = url => {
      if (url.pathname === '/api/forecast') return json({ text: 'Прогноз.', locale: 'ru' })
      expect(url.pathname).toBe('/api/signs/meta')
      const language = url.searchParams.get('locale')
      if (language === 'en') return oldNames.promise
      if (language === 'ru') return json({ error: 'offline' }, 503)
      return json({ locale: 'uk', items: [{ key: 'aries', name: 'Овен (метадані)', is_active: true }] })
    }
    await open('/')
    expect(wrapper.get('h1').text()).toBe('Today’s horoscope')
    await select('uk')
    expect(wrapper.get('h1').text()).toBe('Гороскоп на сьогодні')
    expect(document.documentElement.lang).toBe('uk')
    expect(document.title).toBe('Щоденний гороскоп')
    expect(wrapper.get('label[for="language-select"]').text()).toBe('Мова')
    expect(wrapper.findAll('option').map(node => node.attributes('lang'))).toEqual(['en', 'uk', 'ru'])
    const aries = wrapper.get('.wheel-sign')
    await aries.trigger('focus')
    expect(aries.attributes('aria-label')).toBe('Овен (метадані)')
    expect(aries.attributes('aria-description')).toMatch(/квіт/)
    expect(wrapper.get('.wheel-tooltip-center').text()).toContain('Відкрити гороскоп')
    oldNames.resolve(json({ locale: 'en', items: [{ key: 'aries', name: 'Late name', is_active: true }] }))
    await flushPromises()
    expect(aries.attributes('aria-label')).toBe('Овен (метадані)')
    await select('ru')
    expect(aries.attributes('aria-label')).toBe('Овен')
    expect(wrapper.get('.wheel-tooltip-center').text()).toContain('Открыть гороскоп')
    await aries.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/horoscope/aries/2026-11-22?lang=ru')
  })

  it('invalidates both forecast and latest reads when language changes on a dated page', async () => {
    const enLatest = pendingResponse()
    const ukForecast = pendingResponse()
    read = url => {
      const locale = url.searchParams.get('locale')
      if (url.pathname === '/api/forecast') {
        if (locale === 'en') return json({ error: 'forecast_not_published' }, 404)
        if (locale === 'uk') return ukForecast.promise
        return json({ text: 'Текст публикации.', locale: 'ru' })
      }
      expect(url.searchParams.get('include_latest')).toBe('1')
      expect(locale).toBe('en')
      return enLatest.promise
    }
    await open('/horoscope/gemini/2026-11-22')
    expect(wrapper.text()).toContain('No forecast has been published for this date.')
    await select('uk')
    expect(wrapper.text()).toContain('Завантаження прогнозу…')
    expect(wrapper.find('[aria-label="Наступний день"]').exists()).toBe(true)
    await select('ru')
    enLatest.resolve(json({ latest_published_date: '2026-11-20' }))
    ukForecast.resolve(json({ text: 'Старий прогноз.', locale: 'uk' }))
    await flushPromises()
    expect(wrapper.text()).toContain('Текст публикации.')
    expect(wrapper.text()).not.toContain('Старий прогноз.')
    expect(wrapper.find('time').exists()).toBe(false)
    expect(wrapper.get('h1').text()).toContain('Близнецы')
    expect(wrapper.get('h1').text()).toContain('Сегодня')
    expect(wrapper.findAll('nav a').map(a => a.attributes('href'))).toEqual([
      '/?lang=ru', '/archive/gemini/2026/11?lang=ru',
    ])
  })

  it('discards obsolete years and month availability on a same-URL-path language switch', async () => {
    const years = pendingResponse()
    const availability = pendingResponse()
    read = url => {
      const oldScope = url.searchParams.get('locale') === 'ru'
      if (url.pathname === '/api/years') return oldScope ? years.promise : json([2026])
      if (oldScope) return availability.promise
      return json({ days: [{ date: '2026-11-21', has_forecast: true }] })
    }
    await open('/archive/gemini/2026/11?lang=ru')
    await select('uk')
    expect(wrapper.get('h1').text()).toBe('Архів гороскопів')
    const dates = () => wrapper.get('[aria-label="Календар архіву"]').findAll('a').map(a => a.attributes('href'))
    expect(dates()).toEqual(['/horoscope/gemini/2026-11-21?lang=uk'])
    years.resolve(json([2023]))
    availability.resolve(json({ days: [{ date: '2026-11-01', has_forecast: true }] }))
    await flushPromises()
    expect(dates()).toEqual(['/horoscope/gemini/2026-11-21?lang=uk'])
    expect(wrapper.get('h1').text()).toBe('Архів гороскопів')
    expect(wrapper.text()).toContain('Близнюків')
  })

  it.each([
    ['/horoscope/aries/2026-02-30?lang=uk', 'Такий день не знайдено', 'uk'],
    ['/archive/aries/2026/13?lang=ru', 'Такой месяц не найден', 'ru'],
    ['/archive/missing/2026/11/1', 'Zodiac sign not found', 'en'],
  ])('reports the contextual route error in the language of %s', async (path, message, locale) => {
    read = vi.fn()
    await open(path)
    expect(wrapper.get('h1').text()).toBe(message)
    expect(wrapper.get('a').attributes('href')).toBe(locale === 'en' ? '/' : `/?lang=${locale}`)
    expect(router.currentRoute.value.fullPath).toBe(path)
    expect(read).not.toHaveBeenCalled()
  })
})
