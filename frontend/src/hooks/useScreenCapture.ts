import { useCallback, useRef, useState } from 'react'
import type { RefObject } from 'react'

export interface ScreenCaptureStartResult {
  started: boolean
  displaySurface: 'monitor' | 'window' | 'browser' | 'unknown'
}

export interface ScreenCaptureResult {
  videoRef: RefObject<HTMLVideoElement | null>
  isSharing: boolean
  error: string | null
  surfaceWarning: string | null
  displaySurface: ScreenCaptureStartResult['displaySurface']
  startSharing: () => Promise<ScreenCaptureStartResult>
  stopSharing: () => void
}

function captureIsAllowedHere() {
  return window.isSecureContext || ['localhost', '127.0.0.1'].includes(window.location.hostname)
}

export function useScreenCapture(onTrackEnded: () => void): ScreenCaptureResult {
  const [isSharing, setIsSharing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [surfaceWarning, setSurfaceWarning] = useState<string | null>(null)
  const [displaySurface, setDisplaySurface] = useState<ScreenCaptureStartResult['displaySurface']>('unknown')
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const intentionalStopRef = useRef(false)
  const endedCallbackRef = useRef(onTrackEnded)
  endedCallbackRef.current = onTrackEnded

  const stopSharing = useCallback(() => {
    intentionalStopRef.current = true
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
    setIsSharing(false)
  }, [])

  const startSharing = useCallback(async (): Promise<ScreenCaptureStartResult> => {
    setError(null)
    setSurfaceWarning(null)
    const existing = streamRef.current
    if (existing?.active) return { started: true, displaySurface }
    if (!navigator.mediaDevices?.getDisplayMedia) {
      setError('This browser does not support the screen sharing needed for focus monitoring.')
      return { started: false, displaySurface: 'unknown' }
    }
    if (!captureIsAllowedHere()) {
      setError('Screen monitoring requires HTTPS outside localhost.')
      return { started: false, displaySurface: 'unknown' }
    }

    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getDisplayMedia({
        video: { displaySurface: 'monitor', frameRate: { ideal: 5, max: 10 } },
        audio: false,
      })
    } catch (captureError) {
      const denied = captureError instanceof DOMException && captureError.name === 'NotAllowedError'
      setError(denied
        ? 'Screen sharing was not granted, so the focus task has not started.'
        : captureError instanceof Error ? captureError.message : 'Unable to start screen sharing.')
      return { started: false, displaySurface: 'unknown' }
    }

    stream.getAudioTracks().forEach((track) => {
      track.stop()
      stream.removeTrack(track)
    })
    const track = stream.getVideoTracks()[0]
    const settings = track?.getSettings() as MediaTrackSettings & { displaySurface?: string }
    const surface = settings.displaySurface === 'monitor' || settings.displaySurface === 'window' ||
      settings.displaySurface === 'browser' ? settings.displaySurface : 'unknown'
    if (surface !== 'monitor') {
      setSurfaceWarning('Only the selected window or tab is visible. Work in other apps cannot be evaluated.')
    }
    intentionalStopRef.current = false
    track?.addEventListener('ended', () => {
      streamRef.current = null
      if (videoRef.current) videoRef.current.srcObject = null
      setIsSharing(false)
      if (!intentionalStopRef.current) endedCallbackRef.current()
    }, { once: true })

    streamRef.current = stream
    const video = videoRef.current
    if (video) {
      video.srcObject = stream
      if (video.readyState < 1) {
        await new Promise<void>((resolve) => video.addEventListener('loadedmetadata', () => resolve(), { once: true }))
      }
      try { await video.play() } catch { /* muted hidden video can safely ignore autoplay rejection */ }
    }
    setDisplaySurface(surface)
    setIsSharing(true)
    return { started: true, displaySurface: surface }
  }, [displaySurface])

  return { videoRef, isSharing, error, surfaceWarning, displaySurface, startSharing, stopSharing }
}
