import { useCallback, useEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'
import { captureVideoFrame } from '../lib/capture'

interface QueuedFrame {
  frameId: string
  blob: Blob
  capturedAt: string
  elapsedSeconds: number
  width: number
  height: number
  retriesLeft: number
}

async function uploadFrame(sessionId: string, frame: QueuedFrame) {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 6000)
  let response: Response
  try {
    response = await fetch(`/api/v1/focus-sessions/${sessionId}/frames`, {
      method: 'POST',
      credentials: 'same-origin',
      signal: controller.signal,
      headers: {
        'Content-Type': 'image/jpeg',
        'X-Frame-Id': frame.frameId,
        'X-Captured-At': frame.capturedAt,
        'X-Elapsed-Seconds': String(frame.elapsedSeconds),
        'X-Frame-Width': String(frame.width),
        'X-Frame-Height': String(frame.height),
      },
      body: frame.blob,
    })
  } finally {
    window.clearTimeout(timeout)
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: { message?: string } } | null
    throw new Error(body?.error?.message ?? `Screen sample upload failed (${response.status})`)
  }
}

export function useFrameSampler({ sessionId, videoRef, enabled, startedAt, intervalMs }: {
  sessionId: string | null
  videoRef: RefObject<HTMLVideoElement | null>
  enabled: boolean
  startedAt: number | null
  intervalMs: number
}) {
  const [capturedCount, setCapturedCount] = useState(0)
  const [uploadedCount, setUploadedCount] = useState(0)
  const [pendingCount, setPendingCount] = useState(0)
  const [lastCaptureAt, setLastCaptureAt] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const queueRef = useRef<QueuedFrame[]>([])
  const captureInFlightRef = useRef(false)
  const drainPromiseRef = useRef<Promise<void> | null>(null)

  const drainQueue = useCallback(async () => {
    if (!sessionId) return
    if (drainPromiseRef.current) return drainPromiseRef.current
    const promise = (async () => {
      while (queueRef.current.length) {
        const frame = queueRef.current[0]
        try {
          await uploadFrame(sessionId, frame)
          queueRef.current.shift()
          setUploadedCount((count) => count + 1)
          setPendingCount(queueRef.current.length)
        } catch (uploadError) {
          if (frame.retriesLeft > 0) {
            frame.retriesLeft -= 1
            continue
          }
          queueRef.current.shift()
          setPendingCount(queueRef.current.length)
          setError(uploadError instanceof Error
            ? `One screen sample was skipped: ${uploadError.message}`
            : 'One screen sample was skipped.')
        }
      }
    })().finally(() => { drainPromiseRef.current = null })
    drainPromiseRef.current = promise
    return promise
  }, [sessionId])

  const captureOnce = useCallback(async () => {
    const video = videoRef.current
    if (!sessionId || !video || startedAt === null || captureInFlightRef.current) return
    captureInFlightRef.current = true
    try {
      const { blob, width, height } = await captureVideoFrame({ video })
      const captured = Date.now()
      queueRef.current.push({
        frameId: crypto.randomUUID(), blob, capturedAt: new Date(captured).toISOString(),
        elapsedSeconds: Math.max(0, Math.round((captured - startedAt) / 1000)),
        width, height, retriesLeft: 1,
      })
      setCapturedCount((count) => count + 1)
      setPendingCount(queueRef.current.length)
      setLastCaptureAt(captured)
      void drainQueue()
    } catch (captureError) {
      setError(captureError instanceof Error ? captureError.message : 'Unable to sample the shared screen.')
    } finally {
      captureInFlightRef.current = false
    }
  }, [drainQueue, sessionId, startedAt, videoRef])

  useEffect(() => {
    if (!enabled) return
    void captureOnce()
    const timer = window.setInterval(() => void captureOnce(), intervalMs)
    return () => window.clearInterval(timer)
  }, [captureOnce, enabled, intervalMs])

  return {
    capturedCount, uploadedCount, pendingCount, lastCaptureAt, error,
    flushPending: drainQueue,
  }
}
