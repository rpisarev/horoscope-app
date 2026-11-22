import type { Locale } from '../utils/locale'

export async function getSignMetadata(locale: Locale): Promise<ReadonlyMap<string, string>> {
  const query = new URLSearchParams({ locale })
  const response = await fetch(`/api/signs/meta?${query}`)
  if (!response.ok) throw new Error(`sign metadata status ${response.status}`)
  const payload = await response.json()
  if (payload?.locale !== locale || !Array.isArray(payload.items)) throw new Error('Invalid sign metadata response')

  const names = new Map<string, string>()
  for (const item of payload.items) {
    if (item?.is_active !== true) continue
    // The API identifies legacy fallback labels so the UI can use its own translation.
    if (item.name_locale !== undefined && item.name_locale !== locale) continue
    if (typeof item.key !== 'string' || !item.key.trim()) continue
    if (typeof item.name !== 'string' || !item.name.trim()) continue
    names.set(item.key, item.name)
  }
  return names
}
