import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'

const CONFIRM_MESSAGE =
  'This permanently deletes your Compass profile, companion, quests, sessions, evidence, ' +
  'memories, and caches on this device, and takes you back to the very start of onboarding. ' +
  'This cannot be undone. Continue?'

/** Always-reachable "start over" action: same DELETE /me the Settings →
 * Privacy page offers, but one click + a native confirm instead of typing
 * "delete" — handy for demos and quick resets. */
export function ResetButton({ className, label = 'Start over' }: {
  className?: string
  label?: string
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const reset = useMutation({
    mutationFn: () => api('/me', { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.clear()
      navigate('/onboarding/profile')
    },
  })

  return (
    <button
      className={className}
      disabled={reset.isPending}
      onClick={() => {
        if (window.confirm(CONFIRM_MESSAGE)) reset.mutate()
      }}
      title="Clear all Compass data on this device and restart onboarding"
    >
      {reset.isPending ? 'Resetting…' : label}
    </button>
  )
}
