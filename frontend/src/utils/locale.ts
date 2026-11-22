import { computed, inject } from 'vue'
import { routerKey, START_LOCATION, type LocationQuery, type RouteLocationNormalizedLoaded } from 'vue-router'

export type Locale = 'en' | 'uk' | 'ru'

export function localeFromQuery(lang: LocationQuery[string] | undefined): Locale {
  // Repeated keys arrive as an array, including repeated identical values.
  return lang === 'uk' || lang === 'ru' ? lang : 'en'
}

export function localeQuery(locale: Locale): LocationQuery {
  return locale === 'en' ? {} : { lang: locale }
}

export function locationWithLocale(
  route: Pick<RouteLocationNormalizedLoaded, 'path' | 'query' | 'hash'>,
  locale: Locale,
) {
  const { lang, ...otherQuery } = route.query
  return { path: route.path, query: { ...otherQuery, ...localeQuery(locale) }, hash: route.hash }
}

export function useLocale() {
  const router = inject(routerKey, null)
  const route = computed(() => {
    if (!router) return
    const current = router.currentRoute.value
    // A cold convenience link may still be waiting for /api/meta, or have failed.
    return current === START_LOCATION ? router.resolve(router.options.history.location) : current
  })
  const locale = computed(() => localeFromQuery(route.value?.query.lang))

  async function switchLocale(next: Locale) {
    if (!router || !route.value || next === locale.value) return
    const target = locationWithLocale(route.value, next)
    if (router.currentRoute.value === START_LOCATION) {
      // The initial guard has no committed route for a router push. A same-origin
      // document navigation keeps the requested path and gives Back its own entry.
      window.location.assign(window.location.origin + router.resolve(target).href)
      return
    }
    return router.push(target)
  }

  return { locale, switchLocale }
}
