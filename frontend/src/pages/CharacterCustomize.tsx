import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Character } from '../api/types'
import { Companion } from '../components/Companion'
import { Card, ErrorNote, Spinner } from '../components/ui'
import { PixelIcon } from '../components/PixelIcon'

const FIELDS: Record<string, string[]> = {
  palette: ['meadow', 'ember', 'tide', 'dusk', 'citrus', 'orchid'],
  eyes: ['round', 'sparkle', 'sleepy', 'determined'],
  markings: ['none', 'stripes', 'spots', 'patches', 'swirl'],
  accessory: ['none', 'scarf', 'glasses', 'flower', 'headphones', 'satchel', 'bowtie', 'crown'],
  aura: ['none', 'soft-glow', 'sparkles', 'bubbles', 'embers'],
  habitat: ['meadow', 'workshop', 'shore', 'observatory', 'library', 'garden'],
  personality: ['cheerful', 'thoughtful', 'adventurous', 'gentle', 'curious', 'steadfast'],
  voice_tone: ['warm', 'playful', 'calm', 'spirited'],
}

interface Unlocks {
  unlocks: string[]
  evolution_available: boolean
  next_evolution_level: number | null
  dominant_stat: string
  forms: { id: string; label: string; aura: string }[]
}

export function CharacterCustomize() {
  const queryClient = useQueryClient()
  const character = useQuery({ queryKey: ['character'], queryFn: () => api<Character>('/character') })
  const unlocks = useQuery({ queryKey: ['unlocks'], queryFn: () => api<Unlocks>('/character/unlocks') })
  const [patch, setPatch] = useState<Record<string, string>>({})

  const save = useMutation({
    mutationFn: (body: Record<string, string>) => api<Character>('/character', {
      method: 'PATCH', body, ifMatch: character.data?.data.version,
    }),
    onSuccess: () => {
      setPatch({})
      queryClient.invalidateQueries({ queryKey: ['character'] })
      queryClient.invalidateQueries({ queryKey: ['unlocks'] })
    },
  })

  if (character.isPending) return <Spinner />
  if (character.isError) return <ErrorNote error={character.error} />
  const ch = character.data.data
  const preview = { ...ch, ...patch }
  const locked = new Set(
    ['crown'].filter((c) => !(unlocks.data?.data.unlocks ?? []).includes(`accessory:${c}`)))

  return (
    <div className="grid-2">
      <Card title="Customize" status={[`${ch.species}`, `Level ${ch.level}`]}>
        <label htmlFor="name">Name</label>
        <input id="name" defaultValue={ch.name}
          onChange={(e) => setPatch((p) => ({ ...p, name: e.target.value }))} maxLength={40} />
        <label htmlFor="pronouns">Pronouns</label>
        <select id="pronouns" value={preview.pronouns}
          onChange={(e) => setPatch((p) => ({ ...p, pronouns: e.target.value }))}>
          {['they/them', 'she/her', 'he/him', 'it/its'].map((x) => <option key={x}>{x}</option>)}
        </select>
        {Object.entries(FIELDS).map(([field, values]) => (
          <div key={field}>
            <label htmlFor={field}>{field.replace('_', ' ')}</label>
            <select id={field} value={(preview as unknown as Record<string, string>)[field]}
              onChange={(e) => setPatch((p) => ({ ...p, [field]: e.target.value }))}>
              {values.map((v) => (
                <option key={v} value={v} disabled={field === 'accessory' && locked.has(v)}>
                  {v}{field === 'accessory' && locked.has(v) ? ' (locked)' : ''}
                </option>
              ))}
            </select>
          </div>
        ))}
        <ErrorNote error={save.error} />
        <div className="row" style={{ marginTop: '0.8rem' }}>
          <button className="primary" onClick={() => save.mutate(patch)}
            disabled={save.isPending || Object.keys(patch).length === 0}>Save</button>
        </div>
      </Card>
      <div>
        <Card title="Preview" status={[`${preview.palette} coat`, `${preview.aura} habitat`]}>
          <Companion character={preview} size={240} />
        </Card>
        <Card title="Evolution" status={[`Stage ${ch.evolution_stage}`]}>
          {unlocks.data?.data.evolution_available ? (
            <>
              <p><PixelIcon name="sparkle" /> {ch.name} can evolve! Both forms are purely cosmetic and previous looks stay
                available forever.</p>
              {unlocks.data.data.forms.map((f) => (
                <button key={f.id} className="primary" style={{ marginRight: 8 }}
                  onClick={() => save.mutate({ evolve: f.id, aura: f.aura })}>
                  {f.label}
                </button>
              ))}
            </>
          ) : (
            <p className="muted">
              Next evolution at level {unlocks.data?.data.next_evolution_level ?? '—'}
              {' '}(you're level {ch.level}). Evolutions are cosmetic gifts, never pressure.
            </p>
          )}
        </Card>
      </div>
    </div>
  )
}
