import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { GameEvent } from '../api/types'

/** Event type -> query keys to invalidate. One socket for the whole app. */
const INVALIDATIONS: Record<string, string[][]> = {
  'job.updated': [['jobs'], ['onboarding'], ['interest']],
  'connection.updated': [['connections'], ['onboarding'], ['interest']],
  'character.updated': [['character'], ['unlocks']],
  'reaction.created': [['memories']],
  'quest.updated': [['quests'], ['quest']],
  'focus.updated': [['session'], ['sessions'], ['quests'], ['quest']],
  'verification.updated': [['session'], ['sessions'], ['character'], ['quest'], ['quests']],
  'battle.updated': [['battle']],
  'battle.countdown': [['battle']],
  'battle.completed': [['battle'], ['character']],
  'party.updated': [['party'], ['parties']],
  'boss.updated': [['party'], ['parties'], ['boss']],
  'boss.defeated': [['party'], ['parties'], ['boss'], ['character'], ['memories']],
  'free_model.updated': [['free-models']],
}

export function useWs(enabled: boolean, onEvent?: (event: GameEvent) => void) {
  const queryClient = useQueryClient()
  const cursor = useRef(0)
  const handler = useRef(onEvent)
  handler.current = onEvent

  useEffect(() => {
    if (!enabled) return
    let socket: WebSocket | null = null
    let closed = false
    let retryDelay = 1000

    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      socket = new WebSocket(`${proto}://${location.host}/api/v1/ws?after=${cursor.current}`)
      socket.onmessage = (msg) => {
        let event: GameEvent
        try {
          event = JSON.parse(msg.data)
        } catch {
          return
        }
        if (event.type === 'ping') return
        if (typeof event.id === 'number') cursor.current = Math.max(cursor.current, event.id)
        retryDelay = 1000
        for (const key of INVALIDATIONS[event.type] ?? []) {
          queryClient.invalidateQueries({ queryKey: key })
        }
        handler.current?.(event)
      }
      socket.onclose = () => {
        if (closed) return
        setTimeout(connect, retryDelay)
        retryDelay = Math.min(retryDelay * 2, 15000)
      }
    }
    connect()
    return () => {
      closed = true
      socket?.close()
    }
  }, [enabled, queryClient])
}
