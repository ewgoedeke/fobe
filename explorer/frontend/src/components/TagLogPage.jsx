import React, { useState, useMemo } from 'react'
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  useReactTable,
} from '@tanstack/react-table'
import { useTagLog } from '../api.js'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from './ui/table.jsx'
import { Badge } from './ui/badge.jsx'
import { Button } from './ui/button.jsx'
import { Skeleton } from './ui/skeleton.jsx'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from './ui/select.jsx'
import { ArrowUpDown } from 'lucide-react'

const ACTION_VARIANT = {
  add: 'default',
  remove: 'destructive',
  reclassify: 'secondary',
}

const SOURCE_LABELS = {
  human: 'Human',
  'machine:pretag': 'Pretag',
  'machine:structural': 'Structural',
  'machine:llm': 'LLM',
}

function SortHeader({ column, children }) {
  return (
    <Button
      variant="ghost"
      size="sm"
      className="-ml-3"
      onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
    >
      {children} <ArrowUpDown className="ml-1 size-3" />
    </Button>
  )
}

const columns = [
  {
    accessorKey: 'timestamp',
    header: ({ column }) => <SortHeader column={column}>Time</SortHeader>,
    cell: ({ row }) => {
      const d = new Date(row.original.timestamp)
      return (
        <span className="font-mono text-xs text-muted-foreground">
          {d.toLocaleDateString('en-CA')}{' '}
          {d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
        </span>
      )
    },
    meta: { className: 'w-[140px]' },
  },
  {
    accessorKey: 'user_email',
    header: 'User',
    cell: ({ row }) => (
      <span className="text-sm truncate block" title={row.original.user_email}>
        {row.original.user_email?.split('@')[0] || row.original.user_email}
      </span>
    ),
    meta: { className: 'w-[120px]' },
  },
  {
    accessorKey: 'doc_id',
    header: ({ column }) => <SortHeader column={column}>Document</SortHeader>,
    cell: ({ row }) => (
      <span className="font-mono text-xs truncate block max-w-[280px]">
        {row.original.doc_id}
      </span>
    ),
  },
  {
    accessorKey: 'page_no',
    header: () => <span className="block text-right">Page</span>,
    cell: ({ row }) => (
      <span className="block text-right tabular-nums text-sm">{row.original.page_no}</span>
    ),
    meta: { className: 'w-[56px] text-right' },
  },
  {
    accessorKey: 'action',
    header: 'Action',
    cell: ({ row }) => (
      <Badge variant={ACTION_VARIANT[row.original.action] || 'outline'}>
        {row.original.action}
      </Badge>
    ),
    meta: { className: 'w-[90px]' },
  },
  {
    accessorKey: 'source',
    header: 'Source',
    cell: ({ row }) => {
      const src = row.original.source || 'human'
      const label = SOURCE_LABELS[src] || src
      const isMachine = src.startsWith('machine:')
      return (
        <Badge variant={isMachine ? 'secondary' : 'outline'} className="text-[10px]">
          {label}
        </Badge>
      )
    },
    meta: { className: 'w-[100px]' },
    filterFn: (row, _columnId, filterValue) => {
      if (!filterValue || filterValue === 'all') return true
      return (row.original.source || 'human') === filterValue
    },
  },
  {
    accessorKey: 'element_type',
    header: 'Type',
    cell: ({ row }) => (
      <span className="font-mono text-xs">{row.original.element_type || '\u2014'}</span>
    ),
    meta: { className: 'w-[100px]' },
  },
  {
    accessorKey: 'old_type',
    header: 'Old Type',
    cell: ({ row }) => (
      <span className="font-mono text-xs text-muted-foreground">
        {row.original.old_type || '\u2014'}
      </span>
    ),
    meta: { className: 'w-[100px]' },
  },
]

export default function TagLogPage() {
  const { data: entries = [], isLoading } = useTagLog()
  const [sourceFilter, setSourceFilter] = useState('all')

  const table = useReactTable({
    data: entries,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    state: {
      columnFilters: sourceFilter !== 'all'
        ? [{ id: 'source', value: sourceFilter }]
        : [],
    },
    initialState: {
      sorting: [{ id: 'timestamp', desc: true }],
    },
  })

  // Collect unique sources for the filter dropdown
  const availableSources = useMemo(() => {
    const sources = new Set(entries.map(e => e.source || 'human'))
    return [...sources].sort()
  }, [entries])

  if (isLoading) {
    return (
      <div className="px-4 lg:px-6 py-6 md:py-8 flex flex-col gap-3">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-4 w-48" />
        <div className="flex flex-col gap-2 mt-4">
          {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
        </div>
      </div>
    )
  }

  const filteredCount = table.getFilteredRowModel().rows.length

  return (
    <div className="flex-1 flex flex-col overflow-hidden px-4 lg:px-6 py-6 md:py-8 gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Tag Log</h1>
          <p className="text-sm text-muted-foreground">
            {filteredCount} tagging action{filteredCount !== 1 ? 's' : ''}
            {sourceFilter !== 'all' ? ` (filtered)` : ''} recorded.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Source:</span>
          <Select value={sourceFilter} onValueChange={setSourceFilter}>
            <SelectTrigger className="w-36 h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All sources</SelectItem>
              {availableSources.map(src => (
                <SelectItem key={src} value={src}>
                  {SOURCE_LABELS[src] || src}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="rounded-lg border overflow-auto flex-1">
        <Table className="table-fixed">
          <TableHeader className="bg-muted sticky top-0 z-10">
            {table.getHeaderGroups().map(headerGroup => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map(header => (
                  <TableHead
                    key={header.id}
                    className={header.column.columnDef.meta?.className}
                  >
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="text-center text-muted-foreground py-8">
                  No tagging actions recorded yet.
                </TableCell>
              </TableRow>
            ) : (
              table.getRowModel().rows.map(row => (
                <TableRow key={row.id}>
                  {row.getVisibleCells().map(cell => (
                    <TableCell
                      key={cell.id}
                      className={cell.column.columnDef.meta?.className}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
