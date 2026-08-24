import { useEffect, useRef, useState } from 'react'

/**
 * Approximate the server's current time, derived from the authoritative
 * server_time stamped on the latest payload. Browser timers only render;
 * the server owns all real timestamps.
 */
export function useServerNow(serverTimeIso: string | undefined): number {
  const offset = useRef(0)
  const [, setTick] = useState(0)
  useEffect(() => {
    const interval = setInterval(() => setTick((t) => t + 1), 250)
    return () => clearInterval(interval)
  }, [])
  useEffect(() => {
    if (serverTimeIso) {
      offset.current = new Date(serverTimeIso).getTime() - Date.now()
    }
  }, [serverTimeIso])
  return Date.now() + offset.current
}

export function formatSeconds(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds))
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${String(sec).padStart(2, '0')}`
}
