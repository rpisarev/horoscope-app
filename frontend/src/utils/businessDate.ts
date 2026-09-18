import { readonly, ref } from 'vue'

interface BusinessContext {
  business_date: string
  timezone: string
}

const context = ref<BusinessContext | null>(null)
const error = ref('')
export const businessContext = readonly(context)
export const businessDateError = readonly(error)
let pending: Promise<BusinessContext> | null = null
const REQUEST_TIMEOUT_MS = 5_000

// The server owns "today". Never substitute the browser's calendar or clock.
export function todayIso(): string | null {
  return context.value?.business_date ?? null
}

export function refreshBusinessDate(): Promise<BusinessContext> {
  if (pending) return pending
  const controller = new AbortController()
  let timeoutId: ReturnType<typeof setTimeout>
  const timeout = new Promise<never>((_, reject) => {
    timeoutId = setTimeout(() => {
      reject(new Error('Business date request timed out'))
      controller.abort()
    }, REQUEST_TIMEOUT_MS)
  })

  pending = (async () => {
    try {
      // Bound both the request and body read. A late response cannot replace a newer snapshot.
      const payload = await Promise.race([
        Promise.resolve().then(async () => {
          const response = await fetch('/api/meta', { cache: 'no-store', signal: controller.signal })
          if (!response.ok) throw new Error(`meta status ${response.status}`)
          return response.json()
        }),
        timeout,
      ])
      const day = payload?.business_date
      if (
        typeof day !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(day) ||
        !Number.isFinite(Date.parse(`${day}T00:00:00Z`)) ||
        new Date(`${day}T00:00:00Z`).toISOString().slice(0, 10) !== day ||
        typeof payload.timezone !== 'string' || !payload.timezone.trim()
      ) {
        throw new Error('Invalid business date response')
      }
      context.value = { business_date: day, timezone: payload.timezone }
      error.value = ''
      return context.value
    } catch (cause) {
      error.value = 'Не удалось получить текущую дату. Попробуйте ещё раз.'
      throw cause
    } finally {
      clearTimeout(timeoutId)
      pending = null
    }
  })()
  return pending
}
