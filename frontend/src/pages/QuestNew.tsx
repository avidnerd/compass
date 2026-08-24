import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, idempotencyKey, resetIdempotencyKey } from '../api/client'
import type { Quest } from '../api/types'
import { Card, ErrorNote } from '../components/ui'

export function QuestNew() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [goal, setGoal] = useState('')
  const [meaning, setMeaning] = useState('')
  const [targetDate, setTargetDate] = useState('')
  const [sessionLength, setSessionLength] = useState(25)
  const [share, setShare] = useState(false)

  const create = useMutation({
    mutationFn: () => api<Quest>('/quests', {
      body: {
        goal, meaning: meaning || null, target_date: targetDate || null,
        session_length_minutes: sessionLength, share_category: share,
      },
      idempotencyKey: idempotencyKey('quest-new'),
    }),
    onSuccess: async (resp) => {
      resetIdempotencyKey('quest-new')
      await queryClient.invalidateQueries({ queryKey: ['quests'] })
      navigate(`/quests/${resp.data.id}`)
    },
  })

  return (
    <Card title="What do you want to accomplish?">
      <form onSubmit={(e) => { e.preventDefault(); create.mutate() }}>
        <label htmlFor="goal">Goal</label>
        <input id="goal" value={goal} onChange={(e) => setGoal(e.target.value)} required
          maxLength={300} placeholder="e.g. Finish the draft of my thesis chapter" />
        <label htmlFor="meaning">Why it matters (optional — helps the plan feel human)</label>
        <textarea id="meaning" value={meaning} onChange={(e) => setMeaning(e.target.value)}
          maxLength={300} rows={2} />
        <div className="row">
          <div style={{ flex: 1 }}>
            <label htmlFor="target">Target date (optional)</label>
            <input id="target" type="date" value={targetDate}
              onChange={(e) => setTargetDate(e.target.value)} />
          </div>
          <div style={{ flex: 1 }}>
            <label htmlFor="len">Preferred session length (min)</label>
            <input id="len" type="number" min={5} max={120} value={sessionLength}
              onChange={(e) => setSessionLength(Number(e.target.value))} />
          </div>
        </div>
        <label className="row" style={{ fontWeight: 400 }}>
          <input type="checkbox" style={{ width: 'auto' }} checked={share}
            onChange={(e) => setShare(e.target.checked)} />
          Allow a generic activity category (like “writing”) to appear in multiplayer.
          Your goal text itself is never shared.
        </label>
        <ErrorNote error={create.error} />
        <div className="row" style={{ marginTop: '1rem' }}>
          <button className="primary" type="submit" disabled={create.isPending || !goal.trim()}>
            {create.isPending ? 'Creating…' : 'Plan my quest'}
          </button>
        </div>
        <p className="small muted">A verified-free model proposes 3–7 measurable subgoals with an
          evidence plan. You review and edit everything before the quest starts. If free AI is
          unavailable, you get an editable manual plan instead.</p>
      </form>
    </Card>
  )
}
