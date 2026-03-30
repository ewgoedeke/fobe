import React, { useMemo, useState } from 'react'
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table'
import { useDocuments, useDocumentStats, useElementsBrowse } from '../api.js'
import { Badge, GaapBadge } from './ui/badge.jsx'
import {
  Card, CardHeader, CardTitle, CardDescription, CardFooter
} from './ui/card.jsx'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell
} from './ui/table.jsx'
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent,
  DropdownMenuCheckboxItem
} from './ui/dropdown-menu.jsx'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from './ui/select.jsx'
import { Button } from './ui/button.jsx'
import { Input } from './ui/input.jsx'
import { Progress } from './ui/progress.jsx'
import {
  ArrowUpDown, ChevronLeft, ChevronRight,
  ChevronsLeft, ChevronsRight, Columns3
} from 'lucide-react'
import { PdfIndicator } from './ui/pdf-indicator.jsx'
import { useNavigation } from '@/lib/hooks/useNavigation.jsx'

const columns = [
  {
    accessorKey: 'name',
    header: ({ column }) => (
      <Button variant="ghost" size="sm" className="-ml-3"
        onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Document <ArrowUpDown className="ml-1 size-3" />
      </Button>
    ),
    cell: ({ row }) => {
      const showName = row.original.name && row.original.name !== row.original.id
      return (
        <div className="max-w-[350px]">
          <div className="font-medium truncate">{row.original.id}</div>
          {showName && (
            <div className="text-[11px] text-muted-foreground truncate mt-0.5">{row.original.name}</div>
          )}
        </div>
      )
    },
    enableHiding: false,
  },
  {
    accessorKey: 'gaap',
    header: 'GAAP',
    cell: ({ row }) => <GaapBadge gaap={row.original.gaap} />,
    filterFn: (row, id, value) => value === 'all' || row.getValue(id) === value,
  },
  {
    accessorKey: 'page_count',
    header: ({ column }) => (
      <Button variant="ghost" size="sm" className="-ml-3"
        onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Pages <ArrowUpDown className="ml-1 size-3" />
      </Button>
    ),
    cell: ({ row }) => (
      <div className="text-right tabular-nums text-muted-foreground">
        {row.original.page_count || '\u2013'}
      </div>
    ),
  },
  {
    accessorKey: 'table_count',
    header: ({ column }) => (
      <Button variant="ghost" size="sm" className="-ml-3"
        onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Tables <ArrowUpDown className="ml-1 size-3" />
      </Button>
    ),
    cell: ({ row }) => (
      <div className="text-right tabular-nums text-muted-foreground">
        {row.original.table_count || '\u2013'}
      </div>
    ),
  },
  {
    accessorKey: 'tagged_concepts',
    header: ({ column }) => (
      <Button variant="ghost" size="sm" className="-ml-3"
        onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Concepts <ArrowUpDown className="ml-1 size-3" />
      </Button>
    ),
    cell: ({ row }) => {
      const v = row.original.tagged_concepts || 0
      return (
        <div className={`text-right tabular-nums ${v > 0 ? '' : 'text-muted-foreground'}`}>
          {v}
        </div>
      )
    },
  },
  {
    accessorKey: 'coverage',
    header: ({ column }) => (
      <Button variant="ghost" size="sm" className="-ml-3"
        onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Coverage <ArrowUpDown className="ml-1 size-3" />
      </Button>
    ),
    cell: ({ row }) => {
      const pct = row.original.coverage ?? 0
      return (
        <div className="flex items-center gap-2 min-w-[100px]">
          <Progress value={pct} className="h-2 flex-1" />
          <span className="text-xs tabular-nums text-muted-foreground w-10 text-right">
            {pct.toFixed(0)}%
          </span>
        </div>
      )
    },
    sortingFn: (a, b) => (a.original.coverage ?? 0) - (b.original.coverage ?? 0),
  },
  {
    accessorKey: 'conflict_rows',
    header: ({ column }) => (
      <Button variant="ghost" size="sm" className="-ml-3"
        onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Conflicts <ArrowUpDown className="ml-1 size-3" />
      </Button>
    ),
    cell: ({ row }) => {
      const v = row.original.conflict_rows || 0
      return v > 0
        ? <Badge variant="destructive" className="text-[10px]">{v}</Badge>
        : <span className="text-muted-foreground text-xs">{'\u2013'}</span>
    },
  },
  {
    accessorKey: 'primary_types',
    header: 'Statements',
    cell: ({ row }) => {
      const types = row.original.primary_types
      if (!types?.length) return <span className="text-muted-foreground text-xs">{'\u2013'}</span>
      return (
        <div className="flex gap-1.5 flex-wrap">
          {types.map(t => (
            <Badge key={t} variant="outline" className="px-1.5 py-0.5 text-muted-foreground text-[10px]">
              {t}
            </Badge>
          ))}
        </div>
      )
    },
    enableSorting: false,
  },
  {
    accessorKey: 'source',
    header: 'Source',
    cell: ({ row }) => (
      <Badge variant="outline" className="text-[10px] text-muted-foreground">
        {row.original.source === 'ground_truth' ? 'GT' : row.original.source === 'table_classification' ? 'auto' : row.original.source}
      </Badge>
    ),
  },
  {
    accessorKey: 'has_pdf',
    header: 'PDF',
    cell: ({ row }) => (
      <div className="text-center">
        <PdfIndicator hasPdf={row.original.has_pdf} />
      </div>
    ),
    enableSorting: false,
  },
  {
    accessorKey: 'reviewed_pages',
    header: ({ column }) => (
      <Button variant="ghost" size="sm" className="-ml-3"
        onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Reviewed <ArrowUpDown className="ml-1 size-3" />
      </Button>
    ),
    cell: ({ row }) => {
      const v = row.original.reviewed_pages
      return (
        <div className="text-right tabular-nums">
          {v > 0
            ? <span className="text-green-600 dark:text-green-400">{v} pg</span>
            : <span className="text-muted-foreground">{'\u2013'}</span>
          }
        </div>
      )
    },
  },
]

export default function DocumentsPage() {
  const { navigate } = useNavigation()
  const { data: documents = [] } = useDocuments()
  const { data: browseData } = useElementsBrowse()
  const { data: statsData = [] } = useDocumentStats()

  const [sorting, setSorting] = useState([])
  const [columnFilters, setColumnFilters] = useState([])
  const [columnVisibility, setColumnVisibility] = useState({})
  const [pagination, setPagination] = useState({ pageIndex: 0, pageSize: 20 })

  const browseMap = useMemo(() => {
    const map = {}
    if (browseData?.documents) {
      for (const d of browseData.documents) {
        map[d.doc_id] = d
      }
    }
    return map
  }, [browseData])

  const statsMap = useMemo(() => {
    const map = {}
    for (const s of statsData) {
      map[s.doc_id || s.slug] = s
    }
    return map
  }, [statsData])

  const enrichedDocs = useMemo(() => {
    return documents.map(doc => {
      const browse = browseMap[doc.id] || {}
      const stats = statsMap[doc.id] || {}
      const elements = browse.elements || {}
      const reviews = browse.reviews || {}

      let tableCount = 0
      for (const [, data] of Object.entries(elements)) {
        tableCount += (data.tables?.length || 0)
      }

      const reviewedPages = Object.keys(reviews).length
      const primaryTypes = ['PNL', 'SFP', 'OCI', 'CFS', 'SOCIE'].filter(t => elements[t])

      const totalRows = stats.total_rows || 0
      const taggedRows = stats.tagged_rows || 0
      const coverage = totalRows > 0 ? (taggedRows / totalRows) * 100 : 0

      return {
        ...doc,
        gaap: browse.gaap || (doc.id.includes('ugb') ? 'UGB' : doc.id.includes('hgb') ? 'HGB' : 'IFRS'),
        page_count: browse.page_count || 0,
        table_count: stats.table_count || tableCount || doc.tables || 0,
        primary_types: primaryTypes,
        reviewed_pages: reviewedPages,
        source: browse.source || 'unknown',
        total_rows: totalRows,
        tagged_rows: taggedRows,
        coverage,
        conflict_rows: stats.conflict_rows || 0,
      }
    })
  }, [documents, browseMap, statsMap])

  const table = useReactTable({
    data: enrichedDocs,
    columns,
    state: { sorting, columnFilters, columnVisibility, pagination },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onColumnVisibilityChange: setColumnVisibility,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  })

  // Stats
  const gaapCounts = {}
  enrichedDocs.forEach(d => { gaapCounts[d.gaap] = (gaapCounts[d.gaap] || 0) + 1 })
  const totalTables = enrichedDocs.reduce((s, d) => s + d.table_count, 0)
  const withPdf = enrichedDocs.filter(d => d.has_pdf).length
  const totalReviewed = enrichedDocs.filter(d => d.reviewed_pages > 0).length
  const totalRows = enrichedDocs.reduce((s, d) => s + d.total_rows, 0)
  const totalTagged = enrichedDocs.reduce((s, d) => s + d.tagged_rows, 0)
  const avgCoverage = totalRows > 0 ? (totalTagged / totalRows * 100) : 0
  const totalConflicts = enrichedDocs.reduce((s, d) => s + d.conflict_rows, 0)

  return (
    <div className="flex flex-col gap-6 py-6 md:gap-8 md:py-8 overflow-y-auto">
      <div className="px-4 lg:px-6">
        <h1 className="text-xl font-semibold">Documents</h1>
        <p className="text-sm text-muted-foreground">All ingested documents with tagging coverage and quality metrics</p>
      </div>
      {/* Stat cards */}
      <div className="grid grid-cols-1 gap-4 px-4 *:data-[slot=card]:bg-gradient-to-t *:data-[slot=card]:from-primary/5 *:data-[slot=card]:to-card *:data-[slot=card]:shadow-xs *:data-[slot=card]:border lg:px-6 @xl/main:grid-cols-2 @5xl/main:grid-cols-4">
        <Card>
          <CardHeader>
            <CardDescription>Total Documents</CardDescription>
            <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">{enrichedDocs.length}</CardTitle>
          </CardHeader>
          <CardFooter className="text-sm text-muted-foreground">
            {Object.entries(gaapCounts).map(([g, n]) => `${n} ${g}`).join(', ')}
          </CardFooter>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Total Tables</CardDescription>
            <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">{totalTables}</CardTitle>
          </CardHeader>
          <CardFooter className="text-sm text-muted-foreground">
            across {enrichedDocs.length} documents
          </CardFooter>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Coverage</CardDescription>
            <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
              {avgCoverage.toFixed(1)}%
            </CardTitle>
          </CardHeader>
          <CardFooter className="text-sm text-muted-foreground">
            {totalTagged.toLocaleString()} / {totalRows.toLocaleString()} rows tagged
          </CardFooter>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Conflict Rows</CardDescription>
            <CardTitle className={`text-2xl font-semibold tabular-nums @[250px]/card:text-3xl ${totalConflicts > 0 ? 'text-destructive' : ''}`}>
              {totalConflicts}
            </CardTitle>
          </CardHeader>
          <CardFooter className="text-sm text-muted-foreground">
            {totalReviewed} documents reviewed
          </CardFooter>
        </Card>
      </div>

      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 lg:px-6">
        <div className="flex items-center gap-2 flex-1">
          <Input
            placeholder="Filter documents..."
            value={table.getColumn('name')?.getFilterValue() ?? ''}
            onChange={e => table.getColumn('name')?.setFilterValue(e.target.value)}
            className="max-w-sm"
          />
          <Select
            value={table.getColumn('gaap')?.getFilterValue() ?? 'all'}
            onValueChange={v => table.getColumn('gaap')?.setFilterValue(v)}
          >
            <SelectTrigger className="w-[120px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All GAAP</SelectItem>
              <SelectItem value="IFRS">IFRS</SelectItem>
              <SelectItem value="UGB">UGB</SelectItem>
              <SelectItem value="HGB">HGB</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">
            {table.getFilteredRowModel().rows.length} of {enrichedDocs.length}
          </span>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm">
                <Columns3 />
                <span className="hidden lg:inline">Columns</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              {table.getAllColumns()
                .filter(col => typeof col.accessorFn !== 'undefined' && col.getCanHide())
                .map(col => (
                  <DropdownMenuCheckboxItem
                    key={col.id}
                    className="capitalize"
                    checked={col.getIsVisible()}
                    onCheckedChange={v => col.toggleVisibility(!!v)}
                  >
                    {col.id.replace(/_/g, ' ')}
                  </DropdownMenuCheckboxItem>
                ))
              }
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* Data table */}
      <div className="relative flex flex-col gap-4 px-4 lg:px-6">
        <div className="overflow-hidden rounded-lg border">
          <Table>
            <TableHeader className="bg-muted sticky top-0 z-10">
              {table.getHeaderGroups().map(headerGroup => (
                <TableRow key={headerGroup.id}>
                  {headerGroup.headers.map(header => (
                    <TableHead key={header.id} colSpan={header.colSpan}>
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.header, header.getContext())
                      }
                    </TableHead>
                  ))}
                </TableRow>
              ))}
            </TableHeader>
            <TableBody>
              {table.getRowModel().rows?.length ? (
                table.getRowModel().rows.map(row => (
                  <TableRow
                    key={row.id}
                    className="cursor-pointer"
                    onClick={() => navigate('elements', { docId: row.original.id })}
                  >
                    {row.getVisibleCells().map(cell => (
                      <TableCell key={cell.id}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={columns.length} className="h-24 text-center text-muted-foreground">
                    No documents match your filters.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between">
          <div className="hidden text-sm text-muted-foreground lg:block">
            {table.getFilteredRowModel().rows.length} document(s) total
          </div>
          <div className="flex w-full items-center gap-6 lg:w-fit">
            <div className="hidden items-center gap-2 lg:flex">
              <span className="text-sm font-medium">Rows per page</span>
              <Select
                value={String(table.getState().pagination.pageSize)}
                onValueChange={v => table.setPageSize(Number(v))}
              >
                <SelectTrigger size="sm" className="w-[70px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {[10, 20, 30, 50].map(size => (
                    <SelectItem key={size} value={String(size)}>{size}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex w-fit items-center justify-center text-sm font-medium">
              Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount()}
            </div>
            <div className="ml-auto flex items-center gap-2 lg:ml-0">
              <Button variant="outline" size="icon-sm"
                onClick={() => table.setPageIndex(0)}
                disabled={!table.getCanPreviousPage()}>
                <ChevronsLeft />
              </Button>
              <Button variant="outline" size="icon-sm"
                onClick={() => table.previousPage()}
                disabled={!table.getCanPreviousPage()}>
                <ChevronLeft />
              </Button>
              <Button variant="outline" size="icon-sm"
                onClick={() => table.nextPage()}
                disabled={!table.getCanNextPage()}>
                <ChevronRight />
              </Button>
              <Button variant="outline" size="icon-sm"
                onClick={() => table.setPageIndex(table.getPageCount() - 1)}
                disabled={!table.getCanNextPage()}>
                <ChevronsRight />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
