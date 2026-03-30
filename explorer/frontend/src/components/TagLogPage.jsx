import React from 'react'
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table'
import { useTagLog } from '../api.js'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from './ui/table.jsx'
import { Badge } from './ui/badge.jsx'
import { Button } from './ui/button.jsx'
import { Skeleton } from './ui/skeleton.jsx'
import { ArrowUpDown } from 'lucide-react'

const ACTION_VARIANT = {
  add: 'default',
  remove: 'destructive',
  reclassify: 'secondary',
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
    // No fixed width — this column fills remaining space
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

  const table = useReactTable({
    data: entries,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    initialState: {
      sorting: [{ id: 'timestamp', desc: true }],
    },
  })

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

  return (
    <div className="flex-1 flex flex-col overflow-hidden px-4 lg:px-6 py-6 md:py-8 gap-4">
      <div>
        <h1 className="text-xl font-semibold">Tag Log</h1>
        <p className="text-sm text-muted-foreground">
          {entries.length} tagging action{entries.length !== 1 ? 's' : ''} recorded.
        </p>
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
