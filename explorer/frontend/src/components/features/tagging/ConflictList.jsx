import React from 'react'
import { useVoteConflicts } from '@/api.js'
import { Badge } from '@/components/ui/badge.jsx'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell
} from '@/components/ui/table.jsx'

/**
 * Table listing targets with voting disagreements for a document.
 * Props: docId
 */
export default function ConflictList({ docId }) {
  const { data: conflicts = [], isLoading } = useVoteConflicts(docId)

  if (isLoading) return <div className="text-sm text-muted-foreground p-4">Loading conflicts...</div>
  if (conflicts.length === 0) {
    return <div className="text-sm text-muted-foreground p-4">No voting conflicts for this document.</div>
  }

  return (
    <div className="rounded-lg border overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Target</TableHead>
            <TableHead>Resolved Value</TableHead>
            <TableHead className="text-right">Agree</TableHead>
            <TableHead className="text-right">Dissent</TableHead>
            <TableHead className="text-right">Confidence</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {conflicts.map(c => (
            <TableRow key={c.id}>
              <TableCell className="font-mono text-xs truncate max-w-48">
                {c.target_id}
              </TableCell>
              <TableCell>
                <Badge variant="outline" className="text-[10px]">
                  {c.resolved_value || '–'}
                </Badge>
              </TableCell>
              <TableCell className="text-right tabular-nums text-green-600 dark:text-green-400">
                {c.agree_count}
              </TableCell>
              <TableCell className="text-right tabular-nums text-destructive">
                {c.dissent_count}
              </TableCell>
              <TableCell className="text-right tabular-nums text-muted-foreground">
                {c.confidence != null ? `${(c.confidence * 100).toFixed(0)}%` : '–'}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
