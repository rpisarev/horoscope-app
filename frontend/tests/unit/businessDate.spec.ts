import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

beforeEach(() => {
  vi.resetModules()
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2040-05-01T12:00:00Z'))
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

const payload = (day: string) => ({ business_date: day, timezone: 'Europe/Kyiv' })
const meta = (day: string) => ({ ok: true, json: async () => payload(day) })

describe('authoritative business date', () => {
  it('has no browser-clock fallback before metadata loads', async () => {
    const { todayIso } = await import('../../src/utils/businessDate')
    expect(todayIso()).toBeNull()
  })

  it('deduplicates concurrent loads and requests uncached server metadata', async () => {
    const { refreshBusinessDate, todayIso, businessContext } = await import('../../src/utils/businessDate')
    const fetch = vi.fn().mockResolvedValue(meta('2026-07-16'))
    vi.stubGlobal('fetch', fetch)
    const first = refreshBusinessDate()
    const second = refreshBusinessDate()
    expect(second).toBe(first)
    await Promise.all([first, second])
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledWith('/api/meta', expect.objectContaining({ cache: 'no-store', signal: expect.any(AbortSignal) }))
    expect(todayIso()).toBe('2026-07-16')
    expect(businessContext.value?.timezone).toBe('Europe/Kyiv')
  })

  it.each([
    { ok: false, status: 503 },
    { ok: true, json: async () => payload('2026-02-30') },
    { ok: true, json: async () => ({ business_date: '2026-07-16' }) },
  ])('reports metadata failure without inventing a date', async response => {
    const { refreshBusinessDate, todayIso, businessDateError } = await import('../../src/utils/businessDate')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
    await expect(refreshBusinessDate()).rejects.toThrow()
    expect(businessDateError.value).not.toBe('')
    expect(todayIso()).toBeNull()
  })

  it.each([new Error('offline'), new DOMException('Aborted', 'AbortError')])(
    'keeps the last server value on refresh failure/abort and can recover', async cause => {
      const { refreshBusinessDate, todayIso, businessDateError } = await import('../../src/utils/businessDate')
      const fetch = vi.fn()
        .mockResolvedValueOnce(meta('2026-07-15'))
        .mockRejectedValueOnce(cause)
        .mockResolvedValueOnce(meta('2026-07-16'))
      vi.stubGlobal('fetch', fetch)
      await refreshBusinessDate()
      await expect(refreshBusinessDate()).rejects.toThrow(cause.message)
      expect(todayIso()).toBe('2026-07-15')
      await refreshBusinessDate()
      expect(todayIso()).toBe('2026-07-16')
      expect(businessDateError.value).toBe('')
    }
  )

  it.each(['fetch', 'body'])('times out a stalled %s, releases the request, and allows a fresh retry', async stage => {
    const { refreshBusinessDate, todayIso, businessDateError } = await import('../../src/utils/businessDate')
    let settle: (value: unknown) => void
    // Deliberately ignore abort to verify even a late completion cannot overwrite a retry.
    const stalled = new Promise(resolve => { settle = resolve })
    const fetch = vi.fn()
      .mockReturnValueOnce(stage === 'fetch' ? stalled : Promise.resolve({ ok: true, json: () => stalled }))
      .mockResolvedValueOnce(meta('2026-07-16'))
    vi.stubGlobal('fetch', fetch)
    const request = refreshBusinessDate()
    expect(refreshBusinessDate()).toBe(request)
    const failure = expect(request).rejects.toThrow('Business date request timed out')

    await vi.advanceTimersByTimeAsync(5_000)
    await failure
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch.mock.calls[0][1].signal.aborted).toBe(true)
    expect(businessDateError.value).not.toBe('')
    expect(todayIso()).toBeNull()

    await refreshBusinessDate()
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(todayIso()).toBe('2026-07-16')
    expect(businessDateError.value).toBe('')

    settle!(stage === 'fetch' ? meta('2026-07-15') : payload('2026-07-15'))
    await vi.advanceTimersByTimeAsync(0)
    expect(todayIso()).toBe('2026-07-16')
    expect(businessDateError.value).toBe('')
  })

  it('retains the last successful snapshot when a later refresh times out', async () => {
    const { refreshBusinessDate, businessContext, businessDateError } = await import('../../src/utils/businessDate')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(meta('2026-07-15')).mockReturnValue(new Promise(() => {})))
    await refreshBusinessDate()
    const failure = expect(refreshBusinessDate()).rejects.toThrow('timed out')
    await vi.advanceTimersByTimeAsync(5_000)
    await failure
    expect(businessContext.value).toEqual(payload('2026-07-15'))
    expect(businessDateError.value).not.toBe('')
  })
})
