import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Character, InterestProfile } from '../api/types'
import { Companion } from '../components/Companion'
import { Card, ErrorNote } from '../components/ui'
import { StepDots } from './OnboardingProfile'

const SPECIES = [
  { id: 'sproutling', label: 'Sproutling', blurb: 'A leafy optimist. Grows with every session.' },
  { id: 'emberfox', label: 'Emberfox', blurb: 'Warm, quick, a little dramatic about naps.' },
  { id: 'tidepup', label: 'Tidepup', blurb: 'Calm and steady, loves a good rhythm.' },
]
const PALETTES = ['meadow', 'ember', 'tide', 'dusk', 'citrus', 'orchid']
const EYES = ['round', 'sparkle', 'sleepy', 'determined']
const MARKINGS = ['none', 'stripes', 'spots', 'patches', 'swirl']
const ACCESSORIES = ['none', 'scarf', 'glasses', 'flower', 'headphones', 'satchel', 'bowtie']
const HABITATS = ['meadow', 'workshop', 'shore', 'observatory', 'library', 'garden']
const PERSONALITIES = ['cheerful', 'thoughtful', 'adventurous', 'gentle', 'curious', 'steadfast']
const TONES = ['warm', 'playful', 'calm', 'spirited']

export function OnboardingCompanion() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const interest = useQuery({
    queryKey: ['interest'],
    queryFn: () => api<InterestProfile>('/interest-profile'),
    retry: false,
  })
  const suggestion = interest.data?.data

  const [species, setSpecies] = useState('sproutling')
  const [name, setName] = useState('')
  const [pronouns, setPronouns] = useState('they/them')
  const [palette, setPalette] = useState<string | null>(null)
  const [eyes, setEyes] = useState('round')
  const [markings, setMarkings] = useState('none')
  const [accessory, setAccessory] = useState<string | null>(null)
  const [habitat, setHabitat] = useState('meadow')
  const [personality, setPersonality] = useState<string | null>(null)
  const [tone, setTone] = useState<string | null>(null)

  const effectivePalette = palette ?? suggestion?.palette ?? 'meadow'
  const effectiveAccessory = accessory ?? suggestion?.accessories?.[0] ?? 'none'
  const effectivePersonality = personality ?? suggestion?.personality_presets?.[0] ?? 'cheerful'
  const effectiveTone = tone ?? suggestion?.tone ?? 'warm'

  const create = useMutation({
    mutationFn: () => api<Character>('/character', {
      body: {
        name: name || suggestion?.name_suggestions?.[0] || 'Pip',
        pronouns, species, palette: effectivePalette, eyes, markings,
        accessory: effectiveAccessory, habitat, personality: effectivePersonality,
        voice_tone: effectiveTone, props: suggestion?.props ?? [],
      },
    }),
    onSuccess: async () => {
      await queryClient.invalidateQueries()
      navigate('/quests/new')
    },
  })

  return (
    <Card title="Choose your companion">
      <StepDots step={3} />
      <div className="grid-2">
        <div>
          <div className="row" role="radiogroup" aria-label="Species">
            {SPECIES.map((s) => (
              <button key={s.id} role="radio" aria-checked={species === s.id}
                className={species === s.id ? 'primary' : ''} onClick={() => setSpecies(s.id)}>
                {s.label}
              </button>
            ))}
          </div>
          <p className="small muted">{SPECIES.find((s) => s.id === species)?.blurb}</p>

          <label htmlFor="cname">Name</label>
          <input id="cname" value={name} onChange={(e) => setName(e.target.value)} maxLength={40}
            placeholder={suggestion?.name_suggestions?.join(' · ') || 'Pip'} />
          <label htmlFor="cpro">Pronouns</label>
          <select id="cpro" value={pronouns} onChange={(e) => setPronouns(e.target.value)}>
            {['they/them', 'she/her', 'he/him', 'it/its'].map((p) => <option key={p}>{p}</option>)}
          </select>
          <label htmlFor="cpal">Palette</label>
          <select id="cpal" value={effectivePalette} onChange={(e) => setPalette(e.target.value)}>
            {PALETTES.map((p) => <option key={p}>{p}</option>)}
          </select>
          <div className="row">
            <div style={{ flex: 1 }}>
              <label htmlFor="ceyes">Eyes</label>
              <select id="ceyes" value={eyes} onChange={(e) => setEyes(e.target.value)}>
                {EYES.map((p) => <option key={p}>{p}</option>)}
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <label htmlFor="cmark">Markings</label>
              <select id="cmark" value={markings} onChange={(e) => setMarkings(e.target.value)}>
                {MARKINGS.map((p) => <option key={p}>{p}</option>)}
              </select>
            </div>
          </div>
          <div className="row">
            <div style={{ flex: 1 }}>
              <label htmlFor="cacc">Accessory</label>
              <select id="cacc" value={effectiveAccessory} onChange={(e) => setAccessory(e.target.value)}>
                {ACCESSORIES.map((p) => <option key={p}>{p}</option>)}
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <label htmlFor="chab">Habitat</label>
              <select id="chab" value={habitat} onChange={(e) => setHabitat(e.target.value)}>
                {HABITATS.map((p) => <option key={p}>{p}</option>)}
              </select>
            </div>
          </div>
          <div className="row">
            <div style={{ flex: 1 }}>
              <label htmlFor="cper">Personality</label>
              <select id="cper" value={effectivePersonality} onChange={(e) => setPersonality(e.target.value)}>
                {PERSONALITIES.map((p) => <option key={p}>{p}</option>)}
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <label htmlFor="ctone">Voice tone</label>
              <select id="ctone" value={effectiveTone} onChange={(e) => setTone(e.target.value)}>
                {TONES.map((p) => <option key={p}>{p}</option>)}
              </select>
            </div>
          </div>
        </div>
        <div>
          <Companion character={{
            species, palette: effectivePalette, eyes, markings,
            accessory: effectiveAccessory, aura: 'none', habitat,
            animation: 'idle', expression: 'content', props: suggestion?.props ?? [],
          }} />
          {suggestion && (
            <p className="small muted">Suggestions come from your (editable) interest profile
              {suggestion.model_id ? ` via ${suggestion.model_id}` : ' via the local fallback'}.</p>
          )}
        </div>
      </div>
      <ErrorNote error={create.error} />
      <div className="row" style={{ marginTop: '1rem' }}>
        <button className="primary" onClick={() => create.mutate()} disabled={create.isPending}>
          Hatch my companion
        </button>
      </div>
    </Card>
  )
}
