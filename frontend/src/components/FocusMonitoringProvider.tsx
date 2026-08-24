/* oxlint-disable react/only-export-components -- provider and its context hook are one public unit */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from '../api/client'
import type { FocusSession } from '../api/types'
import { useFrameSampler } from '../hooks/useFrameSampler'
import { useScreenCapture } from '../hooks/useScreenCapture'

interface FocusMonitoringContextValue {
  session: FocusSession | null
  isSharing: boolean
  shareError: string | null
  frameError: string | null
  surfaceWarning: string | null
  capturedCount: number
  uploadedCount: number
  pendingCount: number
  lastCaptureAt: number | null
  requestScreen: () => Promise<boolean>
  activateSession: (session: FocusSession) => Promise<void>
  requestForSession: (session: FocusSession) => Promise<boolean>
  syncSession: (session: FocusSession) => void
  finishAndStop: () => Promise<void>
  cancelAndStop: () => Promise<void>
  abandonCapture: () => void
}

const FocusMonitoringContext = createContext<FocusMonitoringContextValue | null>(null)

export function FocusMonitoringProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<FocusSession | null>(null)
  const sessionRef = useRef<FocusSession | null>(null)
  const [ending, setEnding] = useState(false)

  const handleTrackEnded = useCallback(() => {
    const current = sessionRef.current
    if (current) {
      setSession((value) => value ? { ...value, monitoring_status: 'stopped' } : value)
      void api<FocusSession>(`/focus-sessions/${current.id}/monitoring:stop`, { body: {} })
    }
  }, [])
  const capture = useScreenCapture(handleTrackEnded)
  const sampler = useFrameSampler({
    sessionId: session?.id ?? null,
    videoRef: capture.videoRef,
    enabled: !!session && session.state === 'running' && capture.isSharing && !ending,
    startedAt: session ? new Date(session.started_at).getTime() : null,
    intervalMs: (session?.monitoring_interval_seconds ?? 20) * 1000,
  })

  const syncSession = useCallback((next: FocusSession) => {
    sessionRef.current = next
    setSession(next)
    if (!['running', 'paused'].includes(next.state)) setEnding(true)
  }, [])

  const requestScreen = useCallback(async () => {
    const result = await capture.startSharing()
    return result.started
  }, [capture])

  const activateSession = useCallback(async (next: FocusSession) => {
    sessionRef.current = next
    setSession(next)
    setEnding(false)
    const response = await api<FocusSession>(`/focus-sessions/${next.id}/monitoring:start`, {
      body: { display_surface: capture.displaySurface },
    })
    syncSession(response.data)
  }, [capture.displaySurface, syncSession])

  const requestForSession = useCallback(async (next: FocusSession) => {
    const result = await capture.startSharing()
    if (!result.started) return false
    sessionRef.current = next
    setSession(next)
    setEnding(false)
    const response = await api<FocusSession>(`/focus-sessions/${next.id}/monitoring:start`, {
      body: { display_surface: result.displaySurface },
    })
    syncSession(response.data)
    return true
  }, [capture, syncSession])

  const finishAndStop = useCallback(async () => {
    setEnding(true)
    await sampler.flushPending()
    const current = sessionRef.current
    if (current?.monitoring_enabled) {
      await api(`/focus-sessions/${current.id}/monitoring:stop`, { body: {} }).catch(() => null)
    }
    capture.stopSharing()
  }, [capture, sampler])

  const abandonCapture = useCallback(() => {
    setEnding(true)
    capture.stopSharing()
    sessionRef.current = null
    setSession(null)
  }, [capture])

  const cancelAndStop = useCallback(async () => {
    await finishAndStop()
    sessionRef.current = null
    setSession(null)
  }, [finishAndStop])

  useEffect(() => {
    const handleCompassEvent = (rawEvent: Event) => {
      const event = rawEvent as CustomEvent<{
        type?: string
        aggregate_id?: string | null
        payload?: Record<string, unknown>
      }>
      const current = sessionRef.current
      if (!current || event.detail?.type !== 'focus.updated' ||
          event.detail.aggregate_id !== current.id || !event.detail.payload) return
      const next = event.detail.payload as unknown as FocusSession
      syncSession(next)
      if (!['running', 'paused'].includes(next.state)) capture.stopSharing()
    }
    window.addEventListener('compass-event', handleCompassEvent)
    return () => window.removeEventListener('compass-event', handleCompassEvent)
  }, [capture, syncSession])

  const value = useMemo<FocusMonitoringContextValue>(() => ({
    session, isSharing: capture.isSharing, shareError: capture.error,
    frameError: sampler.error, surfaceWarning: capture.surfaceWarning,
    capturedCount: Math.max(sampler.capturedCount, session?.frames_captured ?? 0),
    uploadedCount: Math.max(sampler.uploadedCount, session?.frames_captured ?? 0),
    pendingCount: sampler.pendingCount, lastCaptureAt: sampler.lastCaptureAt,
    requestScreen, activateSession, requestForSession, syncSession,
    finishAndStop, cancelAndStop, abandonCapture,
  }), [activateSession, abandonCapture, cancelAndStop, capture.error, capture.isSharing,
    capture.surfaceWarning, finishAndStop, requestForSession, requestScreen,
    sampler.capturedCount, sampler.error, sampler.lastCaptureAt, sampler.pendingCount,
    sampler.uploadedCount, session, syncSession])

  return (
    <FocusMonitoringContext.Provider value={value}>
      {children}
      <video ref={capture.videoRef} autoPlay muted playsInline aria-hidden="true"
        style={{ position: 'fixed', width: 1, height: 1, opacity: 0, pointerEvents: 'none' }} />
    </FocusMonitoringContext.Provider>
  )
}

export function useFocusMonitoring() {
  const value = useContext(FocusMonitoringContext)
  if (!value) throw new Error('useFocusMonitoring must be used inside FocusMonitoringProvider')
  return value
}
