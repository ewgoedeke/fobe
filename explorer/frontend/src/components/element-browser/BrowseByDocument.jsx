import React, { useState, useMemo } from 'react'
import { useDocuments, useDocumentStats } from '@/api.js'
import { Badge, GaapBadge } from '@/components/ui/badge.jsx'
import { Input } from '@/components/ui/input.jsx'
import { Progress } from '@/components/ui/progress.jsx'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '@/components/ui/table.jsx'
import { Search } from 'lucide-react'

export default function BrowseByDocument() {
  const { data: documents = [] } = useDocuments()
  const { data: stats = [] } = useDocumentStats()
  const [filter, setFilter] = useState('')

  const statsMap = useMemo(() => {
    const m = {}
    for (const s of stats) m[s.doc_id || s.slug] = s
    return m
  }, [stats])

  const filtered = useMemo(() => {
    const q = filter.toLowerCase()
    return documents
      .map(d => ({ ...d, ...(statsMap[d.id] || {}) }))
      .filter(d => !q || d.id.toLowerCase().includes(q) || (d.name || '').toLowerCase().includes(q))
  }, [documents, statsMap, filter])

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b">
        <div className="relative max-w-md">
          <Search className="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground" />
          <Input
            placeholder="Filter documents..."
            value={filter}
            onChange={e => setFilter(e.target.value)}
            className="pl-8"
          />
        </div>
        <span className="text-xs text-muted-foreground mt-1 block">{filtered.length} documents</span>
      </div>
      <div className="flex-1 overflow-y-auto">
        <Table>
          <TableHeader className="bg-muted sticky top-0">
            <TableRow>
              <TableHead>Document</TableHead>
              <TableHead>GAAP</TableHead>
              <TableHead className="text-right">Tables</TableHead>
              <TableHead className="text-right">Rows</TableHead>
              <TableHead>Coverage</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map(d => {
              const coverage = d.total_rows > 0 ? (d.tagged_rows / d.total_rows * 100) : 0
              return (
                <TableRow key={d.id}>
                  <TableCell>
                    <div className="text-sm font-medium">{d.id}</div>
                    {d.name && d.name !== d.id && (
                      <div className="text-[11px] text-muted-foreground">{d.name}</div>
                    )}
                  </TableCell>
                  <TableCell>
                    <GaapBadge gaap={d.gaap || (d.id.includes('ugb') ? 'UGB' : 'IFRS')} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {d.table_count || d.tables || '\u2013'}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {d.total_rows || '\u2013'}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2 min-w-[80px]">
                      <Progress value={coverage} className="h-2 flex-1" />
                      <span className="text-xs tabular-nums text-muted-foreground w-8 text-right">
                        {coverage > 0 ? `${coverage.toFixed(0)}%` : '\u2013'}
                      </span>
                    </div>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
