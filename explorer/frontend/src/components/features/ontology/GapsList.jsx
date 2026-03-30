import React, { useState, useMemo } from 'react'
import { useOntologyGaps, useUpdateGap } from '@/api.js'
import { Badge } from '@/components/ui/badge.jsx'
import { Button } from '@/components/ui/button.jsx'
import { Input } from '@/components/ui/input.jsx'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select.jsx'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '@/components/ui/table.jsx'
import { Search, CheckCircle, XCircle, Copy, AlertCircle } from 'lucide-react'

const STATUS_COLORS = {
  open: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  proposed: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
  accepted: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  rejected: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  duplicate: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400',
}

export default function GapsList({ onSelectGap }) {
  const [statusFilter, setStatusFilter] = useState('all')
  const [search, setSearch] = useState('')

  const { data: gaps = [], isLoading } = useOntologyGaps(
    statusFilter === 'all' ? undefined : statusFilter
  )
  const updateGap = useUpdateGap()

  const filtered = useMemo(() => {
    if (!search) return gaps
    const q = search.toLowerCase()
    return gaps.filter(g =>
      (g.row_label || '').toLowerCase().includes(q) ||
      (g.context || '').toLowerCase().includes(q) ||
      (g.document_id || '').toLowerCase().includes(q)
    )
  }, [gaps, search])

  const statusCounts = useMemo(() => {
    const counts = { open: 0, proposed: 0, accepted: 0, rejected: 0, duplicate: 0 }
    for (const g of gaps) counts[g.status] = (counts[g.status] || 0) + 1
    return counts
  }, [gaps])

  const handleStatusChange = (gapId, newStatus) => {
    updateGap.mutate({ gapId, updates: { status: newStatus } })
  }

  if (isLoading) {
    return <div className="p-4 text-sm text-muted-foreground">Loading gaps...</div>
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
          placeholder="Search gaps..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="pl-8"
        />
      </div>

      {/* Table */}
      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
          <AlertCircle className="size-8 mb-2" />
          <p className="text-sm">No gaps found</p>
        </div>
      ) : (
        <div className="rounded-lg border overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Row Label</TableHead>
                <TableHead>Context</TableHead>
                <TableHead>Document</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map(gap => (
                <TableRow
                  key={gap.id}
                  className="cursor-pointer"
                  onClick={() => onSelectGap?.(gap)}
                >
                  <TableCell className="font-medium text-sm max-w-64 truncate">
                    {gap.row_label}
                  </TableCell>
                  <TableCell>
                    {gap.context && (
                      <Badge variant="outline" className="text-[10px]">{gap.context}</Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {gap.document_id || '\u2013'}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={`text-[10px] ${STATUS_COLORS[gap.status]}`}>
                      {gap.status}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1" onClick={e => e.stopPropagation()}>
                      {gap.status === 'open' && (
                        <>
                          <Button
                            variant="ghost" size="icon-sm" title="Mark duplicate"
                            onClick={() => handleStatusChange(gap.id, 'duplicate')}
                          >
                            <Copy className="size-3" />
                          </Button>
                          <Button
                            variant="ghost" size="icon-sm" title="Reject"
                            onClick={() => handleStatusChange(gap.id, 'rejected')}
                            className="text-destructive hover:text-destructive"
                          >
                            <XCircle className="size-3" />
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
