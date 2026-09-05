import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, idempotencyKey, postDocument, resetIdempotencyKey } from '../api/client'
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
  const [docText, setDocText] = useState('')
  const [docName, setDocName] = useState('')

  const fromDocument = useMutation({
    mutationFn: () => postDocument<Quest>('/quests:from-document', docText, {
      'x-file-name': docName || 'pasted.txt',
      'x-quest-goal': goal.slice(0, 300),
    }),
    onSuccess: async (resp) => {
      await queryClient.invalidateQueries({ queryKey: ['quests'] })
      navigate(`/quests/${resp.data.id}`)
    },
  })

  async function readFile(file: File) {
    setDocName(file.name)
    setDocText(await file.text())
  }

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
        <label htmlFor="meaning">Why it matters (optional, helps the plan feel human)</label>
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

      <hr style={{ margin: '1.5rem 0', border: 0, borderTop: '1px solid var(--line, #e5e0d8)' }} />

      <h3 style={{ marginTop: 0 }}>Already have a plan?</h3>
      <p className="small muted">
        If you have a project brief, assignment sheet or task list, upload it instead and Compass
        will use the tasks it already contains rather than inventing its own. A document that
        lists its steps needs no AI at all. Plain text, Markdown or CSV. The text is read once
        to build the plan and never stored.
      </p>

      <label htmlFor="doc-file">Upload a document</label>
      <input id="doc-file" type="file" accept=".txt,.md,.markdown,.csv,.rst,.text,text/plain,text/markdown"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) void readFile(f) }} />

      <label htmlFor="doc-text" style={{ marginTop: '0.8rem' }}>…or paste it</label>
      <textarea id="doc-text" value={docText} rows={6}
        onChange={(e) => { setDocText(e.target.value); setDocName('') }}
        placeholder={'- Implement the parser\n- Benchmark against the reference\n1. Write the report'} />
      {docName && <p className="small muted">Read <code>{docName}</code> ({docText.length} characters).</p>}

      <ErrorNote error={fromDocument.error} />
      <div className="row" style={{ marginTop: '0.6rem' }}>
        <button disabled={fromDocument.isPending || docText.trim().length < 20}
          onClick={() => fromDocument.mutate()}>
          {fromDocument.isPending ? 'Reading…' : 'Build quest from this document'}
        </button>
      </div>
    </Card>
  )
}
