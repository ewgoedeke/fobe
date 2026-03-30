import React from 'react'
import { useVotes } from '@/api.js'
import { Badge } from '@/components/ui/badge.jsx'

/**
 * Shows agree/dissent vote breakdown for a (dimension, targetId).
 * Green = unanimous, amber = has dissent, gray = single voter.
 */
export default function VoteBadge({ dimension, targetId }) {
  const { data } = useVotes(dimension, targetId)
  const consensus = data?.consensus

  if (!consensus || consensus.vote_count === 0) return null

  const { agree_count, dissent_count, total_voters } = consensus
  const variant =
    dissent_count > 0 ? 'warning' :
    total_voters > 1 ? 'success' :
    'secondary'

  // Map variant to classes since shadcn Badge may not have warning/success
  const colorClass =
    dissent_count > 0
      ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400 border-amber-200 dark:border-amber-800'
      : total_voters > 1
        ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400 border-green-200 dark:border-green-800'
        : ''

  return (
    <Badge
      variant="outline"
      className={`text-[10px] tabular-nums cursor-default ${colorClass}`}
      title={`${agree_count} agree, ${dissent_count} dissent, ${total_voters} voter(s). Value: ${consensus.resolved_value || '–'}`}
    >
      {agree_count}/{dissent_count}
    </Badge>
  )
}
