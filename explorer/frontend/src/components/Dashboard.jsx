import { useState, useMemo } from 'react'
import {
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table'
import { useDocuments, useStats, useElementsBrowse, useCorpusHealth, useTagActivity, useEventActivity, useTagLog, useReviewStatus } from '../api.js'
import { Badge, GaapBadge } from './ui/badge.jsx'
import { Button } from './ui/button.jsx'
import {
  Card, CardHeader, CardTitle, CardDescription, CardContent
} from './ui/card.jsx'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from './ui/select.jsx'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell
} from './ui/table.jsx'
import { Tabs, TabsList, TabsTrigger, TabsContent } from './ui/tabs.jsx'
import {
  AlertTriangle, CheckCircle2, ChevronDown, ChevronRight,
  ArrowUpDown, ChevronLeft, ChevronsLeft, ChevronsRight,
} from 'lucide-react'
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from './ui/collapsible.jsx'
import { useNavigation } from '@/lib/hooks/useNavigation.jsx'
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip as ReTooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'

/* ── Shared helpers ───────────────────────────────────────────── */

const ACTION_VARIANT = {
  add: 'default',
  remove: 'destructive',
  reclassify: 'secondary',
}

function SortButton({ column, children }) {
  return (
    <Button variant="ghost" size="sm" className="-ml-3"
      onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
      {children} <ArrowUpDown className="ml-1 size-3" />
    </Button>
  )
}

/* ── DataTable (reusable) ─────────────────────────────────────── */

function DataTable({ data, columns, onRowClick, emptyMessage = 'No data.' }) {
  const [sorting, setSorting] = useState([])
  const [pagination, setPagination] = useState({ pageIndex: 0, pageSize: 10 })

  const table = useReactTable({
    data,
    columns,
    state: { sorting, pagination },
    onSortingChange: setSorting,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  })

  return (
    <div className="flex flex-col gap-4">
      <div className="overflow-hidden rounded-lg border">
        <Table>
          <TableHeader className="bg-muted/80 sticky top-0 z-10">
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
                  className={onRowClick ? 'cursor-pointer hover:bg-muted/50' : 'hover:bg-muted/50'}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                >
                  {row.getVisibleCells().map(cell => (
                    <TableCell key={cell.id} className="py-2">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-24 text-center text-muted-foreground">
                  {emptyMessage}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <div className="hidden text-sm text-muted-foreground lg:block">
          {data.length} row(s) total
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
                {[10, 20, 30].map(size => (
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
  )
}

/* ── Section Cards ────────────────────────────────────────────── */

function StatCard({ label, value, detail, subtext, badge }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription className="text-sm font-medium">{label}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-1">
        <div className="text-4xl font-bold tracking-tight tabular-nums">{value}</div>
        <p className="text-sm font-medium">{detail}</p>
        <div className="text-xs text-muted-foreground">{badge || subtext}</div>
      </CardContent>
    </Card>
  )
}

function SectionCards({ documents, browseData, stats, health }) {
  const docs = browseData?.documents || []

  const totalTables = docs.reduce((sum, d) => {
    const tableCount = Object.values(d.elements || {}).reduce((s, el) => s + (el.tables?.length || 0), 0)
    return sum + tableCount
  }, 0)

  const reviewedDocs = docs.filter(d => d.review?.done).length

  const gaapCounts = {}
  documents.forEach(d => {
    if (d.gaap) gaapCounts[d.gaap] = (gaapCounts[d.gaap] || 0) + 1
  })
  const gaapText = Object.entries(gaapCounts).map(([g, n]) => `${n} ${g}`).join(' / ')

  const issues = health
    ? health.missing_docling.length + health.missing_meta.length + health.broken_table_graphs.length
    : null

  const healthComplete = health
    ? (health.complete != null ? health.complete : health.total - issues)
    : null

  const healthBadge = issues != null && issues > 0
    ? <Badge variant="outline" className="border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400 text-[10px]">{issues} issue{issues !== 1 ? 's' : ''}</Badge>
    : issues === 0
      ? <Badge variant="outline" className="border-green-500/30 bg-green-500/10 text-green-600 dark:text-green-400 text-[10px]">all complete</Badge>
      : null

  return (
    <div className="grid grid-cols-1 gap-6 @xl/main:grid-cols-2 @5xl/main:grid-cols-4">
      <StatCard
        label="Total Documents"
        value={documents.length}
        detail="Across all frameworks"
        subtext={gaapText || 'No GAAP data'}
      />
      <StatCard
        label="Total Tables"
        value={totalTables || '...'}
        detail="Extracted from PDF corpus"
        subtext={`across ${documents.length} documents`}
      />
      <StatCard
        label="Corpus Health"
        value={health ? `${healthComplete}/${health.total}` : '...'}
        detail="Complete fixtures"
        badge={healthBadge}
      />
      <StatCard
        label="Reviewed"
        value={reviewedDocs}
        detail="Manual review progress"
        subtext={`of ${docs.length} documents`}
      />
    </div>
  )
}

/* ── Chart components ─────────────────────────────────────────── */

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg bg-background shadow-md border px-3 py-2">
      <div className="text-xs font-medium text-foreground mb-1">{label}</div>
      {payload.map((entry, i) => (
        <div key={i} className="flex items-center gap-2 text-xs">
          <span className="size-2 rounded-full" style={{ background: entry.color, opacity: entry.strokeOpacity || 1 }} />
          <span className="text-muted-foreground">{entry.name}</span>
          <span className="font-medium ml-auto">{entry.value}</span>
        </div>
      ))}
    </div>
  )
}

function TagActivityChart({ activity }) {
  if (!activity || activity.activity.length === 0) {
    return (
      <div className="text-sm text-muted-foreground py-8 text-center">
        No tagging activity yet
      </div>
    )
  }

  const data = activity.activity

  return (
    <div>
      <div className="h-[280px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
            <defs>
              <linearGradient id="gradAdd" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--color-chart-accent)" stopOpacity={0.4} />
                <stop offset="100%" stopColor="var(--color-chart-accent)" stopOpacity={0.05} />
              </linearGradient>
              <linearGradient id="gradReclassify" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--color-chart-accent)" stopOpacity={0.2} />
                <stop offset="100%" stopColor="var(--color-chart-accent)" stopOpacity={0.02} />
              </linearGradient>
              <linearGradient id="gradRemove" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--color-chart-accent)" stopOpacity={0.08} />
                <stop offset="100%" stopColor="var(--color-chart-accent)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" strokeOpacity={0.5} vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--color-muted-foreground)' }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 11, fill: 'var(--color-muted-foreground)' }} axisLine={false} tickLine={false} allowDecimals={false} />
            <ReTooltip content={<ChartTooltip />} />
            <Area type="natural" dataKey="add" stackId="a" stroke="var(--color-chart-accent)" strokeWidth={1.5} fill="url(#gradAdd)" name="Add" />
            <Area type="natural" dataKey="reclassify" stackId="a" stroke="var(--color-chart-accent)" strokeWidth={1.5} strokeOpacity={0.5} fill="url(#gradReclassify)" name="Reclassify" />
            <Area type="natural" dataKey="remove" stackId="a" stroke="var(--color-chart-accent)" strokeWidth={1.5} strokeOpacity={0.2} fill="url(#gradRemove)" name="Remove" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div className="flex items-center justify-center gap-4 mt-3 text-xs text-muted-foreground">
        <div className="flex items-center gap-1.5">
          <span className="size-2 rounded-full bg-[var(--color-chart-accent)]" />Add
        </div>
        <div className="flex items-center gap-1.5">
          <span className="size-2 rounded-full bg-[var(--color-chart-accent)] opacity-50" />Reclassify
        </div>
        <div className="flex items-center gap-1.5">
          <span className="size-2 rounded-full bg-[var(--color-chart-accent)] opacity-20" />Remove
        </div>
      </div>
      {activity.total_actions > 0 && (
        <div className="text-xs text-muted-foreground mt-2 text-center">
          {activity.total_actions} total actions
        </div>
      )}
    </div>
  )
}

function EventChart({ data, label = 'Count', color = 'var(--color-chart-accent)' }) {
  if (!data || data.length === 0) {
    return <EmptyChartState message="No data available" />
  }
  const total = data.reduce((s, d) => s + d.count, 0)
  const gradId = `gradEvent-${label.replace(/\s/g, '')}`
  return (
    <div>
      <div style={{ height: 280 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
            <defs>
              <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.35} />
                <stop offset="100%" stopColor={color} stopOpacity={0.03} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" strokeOpacity={0.5} vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--color-muted-foreground)' }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 11, fill: 'var(--color-muted-foreground)' }} axisLine={false} tickLine={false} allowDecimals={false} />
            <ReTooltip content={<ChartTooltip />} />
            <Area type="natural" dataKey="count" stroke={color} strokeWidth={2} fill={`url(#${gradId})`} name={label} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div className="text-xs text-muted-foreground mt-2 text-center">
        {total.toLocaleString()} total
      </div>
    </div>
  )
}

function EmptyChartState({ message = 'No data available' }) {
  return (
    <div className="flex items-center justify-center h-[220px] text-sm text-muted-foreground">
      {message}
    </div>
  )
}

/* ── Corpus Health (collapsible detail, stays in right card) ──── */

const FILE_LABELS = {
  docling: 'Docling JSON',
  meta: 'Document Meta',
  table_graphs: 'Table Graphs',
  ground_truth: 'Ground Truth',
  rank_tags: 'Rank Tags',
}

function CorpusHealthSection({ health }) {
  const [expanded, setExpanded] = useState(null)

  if (!health) return null

  const issues = [
    { key: 'missing_docling', label: 'Missing Docling JSON', items: health.missing_docling, severity: 'warning' },
    { key: 'missing_meta', label: 'Missing Document Meta', items: health.missing_meta, severity: 'warning' },
    { key: 'broken_table_graphs', label: 'Broken/Empty Table Graphs', items: health.broken_table_graphs, severity: 'error' },
  ].filter(g => g.items.length > 0)

  if (issues.length === 0) {
    return (
      <div className="flex items-center gap-2 text-sm py-2">
        <CheckCircle2 className="size-4 text-green-600 dark:text-green-400" />
        <span className="text-muted-foreground">All {health.total} fixtures have complete data files</span>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {issues.map(({ key, label, items, severity }) => (
        <Collapsible key={key} open={expanded === key} onOpenChange={(open) => setExpanded(open ? key : null)}>
          <CollapsibleTrigger asChild>
            <button className="w-full flex items-center gap-3 px-4 py-3 text-sm hover:bg-muted/50 rounded-lg transition-colors cursor-pointer border">
              {expanded === key
                ? <ChevronDown className="size-3.5 text-muted-foreground" />
                : <ChevronRight className="size-3.5 text-muted-foreground" />
              }
              <AlertTriangle className={`size-3.5 ${severity === 'error' ? 'text-destructive' : 'text-amber-500'}`} />
              {severity === 'error'
                ? <Badge variant="destructive" className="text-[10px]">{items.length}</Badge>
                : <Badge variant="outline" className="border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400 text-[10px]">{items.length}</Badge>
              }
              <span className="text-muted-foreground">{label}</span>
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="px-4 pb-3 pt-2 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-1.5">
              {items.map(id => (
                <div key={id} className="text-xs text-muted-foreground truncate font-mono" title={id}>
                  {id}
                </div>
              ))}
            </div>
          </CollapsibleContent>
        </Collapsible>
      ))}
    </div>
  )
}

/* ── Column definitions ───────────────────────────────────────── */

const recentDocColumns = [
  {
    accessorKey: 'id',
    header: ({ column }) => <SortButton column={column}>Document</SortButton>,
    cell: ({ row }) => (
      <div>
        <div className="font-medium">{row.original.id}</div>
        {row.original.entity_name && row.original.entity_name !== row.original.id && (
          <div className="text-[11px] text-muted-foreground truncate mt-0.5">{row.original.entity_name}</div>
        )}
      </div>
    ),
  },
  {
    accessorKey: 'gaap',
    header: 'GAAP',
    cell: ({ row }) => row.original.gaap
      ? <GaapBadge gaap={row.original.gaap} />
      : <span className="text-muted-foreground">&ndash;</span>,
  },
  {
    accessorKey: 'page_count',
    header: ({ column }) => <SortButton column={column}>Pages</SortButton>,
    cell: ({ row }) => (
      <div className="text-right tabular-nums text-muted-foreground">
        {row.original.page_count || '\u2013'}
      </div>
    ),
  },
  {
    accessorKey: 'table_count',
    header: ({ column }) => <SortButton column={column}>Tables</SortButton>,
    cell: ({ row }) => (
      <div className="text-right tabular-nums text-muted-foreground">
        {row.original.table_count || '\u2013'}
      </div>
    ),
  },
  {
    accessorKey: 'has_pdf',
    header: 'PDF',
    cell: ({ row }) => (
      <div className="text-center">
        {row.original.has_pdf
          ? <Badge variant="outline" className="border-green-500/30 bg-green-500/10 text-green-600 dark:text-green-400 text-[10px]">PDF</Badge>
          : <span className="text-muted-foreground text-xs">&ndash;</span>
        }
      </div>
    ),
    enableSorting: false,
  },
]

const corpusHealthColumns = [
  {
    accessorKey: 'doc',
    header: ({ column }) => <SortButton column={column}>Document</SortButton>,
    cell: ({ row }) => <span className="font-mono text-xs">{row.original.doc}</span>,
  },
  {
    accessorKey: 'issueType',
    header: 'Issue Type',
    cell: ({ row }) => <span className="text-sm">{row.original.issueType}</span>,
  },
  {
    accessorKey: 'severity',
    header: 'Severity',
    cell: ({ row }) => {
      const s = row.original.severity
      return s === 'error'
        ? <Badge variant="destructive" className="text-[10px]">Error</Badge>
        : <Badge variant="outline" className="border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400 text-[10px]">Warning</Badge>
    },
    enableSorting: false,
  },
]

const recentTagColumns = [
  {
    accessorKey: 'doc_id',
    header: ({ column }) => <SortButton column={column}>Document</SortButton>,
    cell: ({ row }) => <span className="font-mono text-xs truncate block max-w-[280px]">{row.original.doc_id}</span>,
  },
  {
    accessorKey: 'action',
    header: 'Action',
    cell: ({ row }) => (
      <Badge variant={ACTION_VARIANT[row.original.action] || 'outline'}>
        {row.original.action}
      </Badge>
    ),
    enableSorting: false,
  },
  {
    accessorKey: 'element_type',
    header: 'Tag / Concept',
    cell: ({ row }) => <span className="font-mono text-xs">{row.original.element_type || '\u2014'}</span>,
  },
  {
    accessorKey: 'timestamp',
    header: ({ column }) => <SortButton column={column}>Timestamp</SortButton>,
    cell: ({ row }) => {
      const d = new Date(row.original.timestamp)
      return (
        <span className="font-mono text-xs text-muted-foreground">
          {d.toLocaleDateString('en-CA')} {d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
        </span>
      )
    },
  },
]

const reviewQueueColumns = [
  {
    accessorKey: 'id',
    header: ({ column }) => <SortButton column={column}>Document</SortButton>,
    cell: ({ row }) => <span className="font-mono text-xs">{row.original.id}</span>,
  },
  {
    accessorKey: 'gaap',
    header: 'GAAP',
    cell: ({ row }) => row.original.gaap
      ? <GaapBadge gaap={row.original.gaap} />
      : <span className="text-muted-foreground">&ndash;</span>,
  },
  {
    accessorKey: 'total_tables',
    header: ({ column }) => <SortButton column={column}>Tables</SortButton>,
    cell: ({ row }) => (
      <div className="text-right tabular-nums text-muted-foreground">
        {row.original.total_tables || 0}
      </div>
    ),
  },
  {
    accessorKey: 'status',
    header: 'Status',
    cell: ({ row }) => {
      const f = row.original
      if (f.has_manifest && !f.has_human_review)
        return <Badge variant="outline" className="border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400 text-[10px]">Needs Review</Badge>
      return <Badge variant="outline" className="text-[10px]">Pending</Badge>
    },
    enableSorting: false,
  },
]

/* ── Dashboard ────────────────────────────────────────────────── */

export default function Dashboard() {
  const { navigate } = useNavigation()
  const { data: stats } = useStats()
  const { data: documents = [] } = useDocuments()
  const { data: browseData } = useElementsBrowse()
  const { data: health } = useCorpusHealth()
  const { data: activity } = useTagActivity()
  const { data: eventActivity } = useEventActivity()
  const { data: tagLogEntries = [] } = useTagLog()
  const { data: reviewFixtures = [] } = useReviewStatus()

  const healthRows = useMemo(() => {
    if (!health) return []
    const rows = []
    health.missing_docling.forEach(id => rows.push({ doc: id, issueType: 'Missing Docling JSON', severity: 'warning' }))
    health.missing_meta.forEach(id => rows.push({ doc: id, issueType: 'Missing Document Meta', severity: 'warning' }))
    health.broken_table_graphs.forEach(id => rows.push({ doc: id, issueType: 'Broken/Empty Table Graphs', severity: 'error' }))
    return rows
  }, [health])

  const reviewQueue = useMemo(() => {
    return reviewFixtures.filter(f => !f.has_human_review)
  }, [reviewFixtures])

  return (
    <div className="p-6 max-w-7xl mx-auto w-full flex flex-col gap-6 overflow-y-auto">
      <div>
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <p className="text-sm text-muted-foreground">Overview of your document corpus and tagging progress</p>
      </div>
      <SectionCards documents={documents} browseData={browseData} stats={stats} health={health} />

      {/* Activity chart — full width */}
      <Card>
        <Tabs defaultValue="tagging">
          <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-lg font-semibold">Activity</CardTitle>
            <TabsList variant="line">
              <TabsTrigger value="tagging" className="text-xs">Tagging Activity</TabsTrigger>
              <TabsTrigger value="uploads" className="text-xs">Documents Uploaded</TabsTrigger>
              <TabsTrigger value="views" className="text-xs">Page Views</TabsTrigger>
            </TabsList>
          </CardHeader>
          <CardContent>
            <TabsContent value="tagging" className="mt-0">
              <TagActivityChart activity={activity} />
            </TabsContent>
            <TabsContent value="uploads" className="mt-0">
              <EventChart data={eventActivity?.uploads} label="Documents" color="var(--color-chart-accent)" />
            </TabsContent>
            <TabsContent value="views" className="mt-0">
              <EventChart data={eventActivity?.views} label="Page Views" color="var(--color-chart-2, hsl(173 58% 39%))" />
            </TabsContent>
          </CardContent>
        </Tabs>
      </Card>

      {/* Tabbed data tables */}
      <Tabs defaultValue="recent-docs">
        <TabsList>
          <TabsTrigger value="recent-docs">
            Recent Documents
            <Badge variant="secondary" className="ml-1.5 text-[10px] px-1.5 min-w-[1.25rem] h-5">{documents.length}</Badge>
          </TabsTrigger>
          <TabsTrigger value="corpus-health">
            Corpus Health
            <Badge variant="secondary" className="ml-1.5 text-[10px] px-1.5 min-w-[1.25rem] h-5">{healthRows.length}</Badge>
          </TabsTrigger>
          <TabsTrigger value="recent-tags">
            Recent Tags
            <Badge variant="secondary" className="ml-1.5 text-[10px] px-1.5 min-w-[1.25rem] h-5">{tagLogEntries.length}</Badge>
          </TabsTrigger>
          <TabsTrigger value="review-queue">
            Review Queue
            <Badge variant="secondary" className="ml-1.5 text-[10px] px-1.5 min-w-[1.25rem] h-5">{reviewQueue.length}</Badge>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="recent-docs">
          <DataTable
            data={documents}
            columns={recentDocColumns}
            onRowClick={(row) => navigate('elements', { docId: row.original.id })}
            emptyMessage="No documents found."
          />
        </TabsContent>

        <TabsContent value="corpus-health">
          <DataTable
            data={healthRows}
            columns={corpusHealthColumns}
            emptyMessage="No corpus health issues found."
          />
        </TabsContent>

        <TabsContent value="recent-tags">
          <DataTable
            data={tagLogEntries}
            columns={recentTagColumns}
            emptyMessage="No tagging actions recorded yet."
          />
        </TabsContent>

        <TabsContent value="review-queue">
          <DataTable
            data={reviewQueue}
            columns={reviewQueueColumns}
            emptyMessage="No documents pending review."
          />
        </TabsContent>
      </Tabs>
    </div>
  )
}
