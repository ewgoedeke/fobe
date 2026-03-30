import React, { useState, useMemo } from 'react'
import { useConceptProposals, useAcceptProposal, useRejectProposal } from '@/api.js'
import { Badge } from '@/components/ui/badge.jsx'
import { Button } from '@/components/ui/button.jsx'
import { Input } from '@/components/ui/input.jsx'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '@/components/ui/table.jsx'
import { Search, CheckCircle, XCircle, FileText } from 'lucide-react'

const STATUS_COLORS = {
  draft: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400',
  review: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  accepted: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  rejected: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
}

export default function ProposalsList({ onSelectProposal }) {
  const [statusFilter, setStatusFilter] = useState('all')
  const [search, setSearch] = useState('')

  const { data: proposals = [], isLoading } = useConceptProposals(
    statusFilter === 'all' ? undefined : statusFilter
  )
  const acceptProposal = useAcceptProposal()
  const rejectProposal = useRejectProposal()

  const filtered = useMemo(() => {
    if (!search) return proposals
    const q = search.toLowerCase()
    return proposals.filter(p =>
      (p.label || '').toLowerCase().includes(q) ||
      (p.concept_id || '').toLowerCase().includes(q) ||
      (p.context || '').toLowerCase().includes(q)
    )
  }, [proposals, search])

  const statusCounts = useMemo(() => {
    const counts = { draft: 0, review: 0, accepted: 0, rejected: 0 }
    for (const p of proposals) counts[p.status] = (counts[p.status] || 0) + 1
    return counts
  }, [proposals])

  if (isLoading) {
    return <div className="p-4 text-sm text-muted-foreground">Loading proposals...</div>
  }

  return (
    <div className="flex flex-col gap-4 p-4 h-full overflow-y-auto">
      {/* Summary badges */}
      <div className="flex items-center gap-2 flex-wrap">
        {Object.entries(statusCounts).filter(([, c]) => c > 0).map(([status, count]) => (
          <Badge
            key={status}
            variant="outline"
            className={`text-xs cursor-pointer ${STATUS_COLORS[status]} ${statusFilter === status ? 'ring-2 ring-ring' : ''}`}
            onClick={() => setStatusFilter(statusFilter === status ? 'all' : status)}
          >
            {status}: {count}
          </Badge>
        ))}
        {statusFilter !== 'all' && (
          <Button variant="ghost" size="sm" onClick={() => setStatusFilter('all')}>
            Clear filter
          </Button>
        )}
      </div>

      {/* Search */}
      <div className="relative max-w-md">
        <Search className="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground" />
        <Input
          placeholder="Search proposals..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="pl-8"
        />
      </div>

      {/* Table */}
      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
          <FileText className="size-8 mb-2" />
          <p className="text-sm">No proposals yet</p>
        </div>
      ) : (
        <div className="rounded-lg border overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Concept ID</TableHead>
                <TableHead>Label</TableHead>
                <TableHead>Context</TableHead>
                <TableHead>GAAP</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map(p => (
                <TableRow
                  key={p.id}
                  className="cursor-pointer"
                  onClick={() => onSelectProposal?.(p)}
                >
                  <TableCell className="font-mono text-xs">{p.concept_id}</TableCell>
                  <TableCell className="font-medium text-sm">{p.label}</TableCell>
                  <TableCell>
                    {p.context && (
                      <Badge variant="outline" className="text-[10px]">{p.context}</Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {p.gaap || 'All'}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={`text-[10px] ${STATUS_COLORS[p.status]}`}>
                      {p.status}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1" onClick={e => e.stopPropagation()}>
                      {(p.status === 'draft' || p.status === 'review') && (
                        <>
                          <Button
                            variant="ghost" size="icon-sm" title="Accept"
                            onClick={() => acceptProposal.mutate(p.id)}
                            disabled={acceptProposal.isPending}
                          >
                            <CheckCircle className="size-3.5 text-green-600" />
                          </Button>
                          <Button
                            variant="ghost" size="icon-sm" title="Reject"
                            onClick={() => rejectProposal.mutate(p.id)}
                            disabled={rejectProposal.isPending}
                            className="text-destructive hover:text-destructive"
                          >
                            <XCircle className="size-3.5" />
                          </Button>
                        </>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
