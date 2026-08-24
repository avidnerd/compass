import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Character, Memory } from '../api/types'
import { Card, ErrorNote, Meter, Spinner } from '../components/ui'

const KIND_ICON: Record<string, string> = {
  reflection: '💭', encourage: '💌', postcard: '📮', boss: '🐲', battle: '⚔️',
}

export function CharacterJournal() {
  const queryClient = useQueryClient()
  const [editId, setEditId] = useState<string | null>(null)
  const [editText, setEditText] = useState('')

  const character = useQuery({ queryKey: ['character'], queryFn: () => api<Character>('/character') })
  const memories = useQuery({
    queryKey: ['memories'],
    queryFn: () => api<{ items: Memory[] }>('/character/memories'),
  })

  const update = useMutation({
    mutationFn: (vars: { id: string; text: string }) =>
      api(`/character/memories/${vars.id}`, { method: 'PATCH', body: { text: vars.text } }),
    onSuccess: () => {
      setEditId(null)
      queryClient.invalidateQueries({ queryKey: ['memories'] })
    },
  })
  const remove = useMutation({
    mutationFn: (id: string) => api(`/character/memories/${id}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['memories'] }),
  })

  if (character.isPending || memories.isPending) return <Spinner />
  const ch = character.data?.data

  return (
    <div className="grid-2">
      <div>
        <Card title={`${ch?.name}'s journal`}>
          <p className="small muted">Short, editable reflections — never raw work content. Delete
            anything, any time.</p>
          {memories.data?.data.items.length === 0 && <p className="muted">No memories yet.
            Finish a focus session to write the first one together.</p>}
          {memories.data?.data.items.map((m) => (
            <div key={m.id} className="list-item">
              {editId === m.id ? (
                <div style={{ flex: 1 }}>
                  <input value={editText} onChange={(e) => setEditText(e.target.value)} maxLength={300} />
                  <div className="row" style={{ marginTop: 4 }}>
                    <button className="primary" onClick={() => update.mutate({ id: m.id, text: editText })}>Save</button>
                    <button onClick={() => setEditId(null)}>Cancel</button>
                  </div>
                </div>
              ) : (
                <>
                  <span style={{ flex: 1 }}>
                    <span aria-hidden="true">{KIND_ICON[m.kind] ?? '✨'}</span> {m.text}
                    <span className="small muted"> · {new Date(m.created_at).toLocaleDateString()}</span>
                  </span>
                  <span className="row">
                    <button onClick={() => { setEditId(m.id); setEditText(m.text) }}>Edit</button>
                    <button className="danger" onClick={() => remove.mutate(m.id)}>Delete</button>
                  </span>
                </>
              )}
            </div>
          ))}
          <ErrorNote error={update.error || remove.error} />
        </Card>
      </div>
      <div>
        {ch && (
          <Card title="Growth">
            <p className="small muted">Level {ch.level} · {ch.xp} XP · evolution stage {ch.evolution_stage}</p>
            <Meter label="Focus" value={ch.stat_focus} />
            <Meter label="Curiosity" value={ch.stat_curiosity} />
            <Meter label="Craft" value={ch.stat_craft} />
            <Meter label="Communication" value={ch.stat_communication} />
            <Meter label="Collaboration" value={ch.stat_collaboration} />
            <Meter label="Balance" value={ch.stat_balance} />
          </Card>
        )}
        <Card title="Postcards">
          {memories.data?.data.items.filter((m) => m.kind === 'postcard').slice(0, 5).map((m) => (
            <p key={m.id}>📮 {m.text}</p>
          ))}
          {memories.data?.data.items.filter((m) => m.kind === 'postcard').length === 0 && (
            <p className="muted">Your companion writes one postcard per day you focus.</p>
          )}
        </Card>
      </div>
    </div>
  )
}
