import React, { useState, useMemo } from 'react'
import {
  useMachineTagRuns, useMachineTagRun, useMachineTagRunResults,
  useCreateMachineTagRun, useCancelMachineTagRun,
  useDocuments, useGTSets,
} from '../api.js'
import { Badge } from './ui/badge.jsx'
import { Button } from './ui/button.jsx'
import { Input } from './ui/input.jsx'
import { Progress } from './ui/progress.jsx'
import { Card, CardContent, CardHeader, CardTitle } from './ui/card.jsx'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from './ui/select.jsx'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from './ui/table.jsx'
import {
  Play, Square, Plus, ArrowLeft, CheckCircle, XCircle,
  Clock, Loader2, Bot,
} from 'lucide-react'

// ── Status helpers ────────────────────────────────────────

const STATUS_CONFIG = {
  pending: { label: 'Pending', color: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400', icon: Clock },
  running: { label: 'Running', color: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400', icon: Loader2 },
  completed: { label: 'Completed', color: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400', icon: CheckCircle },
  failed: { label: 'Failed', color: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400', icon: XCircle },
  cancelled: { label: 'Cancelled', color: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400', icon: Square },
}

function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.pending
  const Icon = cfg.icon
  return (
    <Badge variant="outline" className={`text-[10px] gap-1 ${cfg.color}`}>
      <Icon className={`size-3 ${status === 'running' ? 'animate-spin' : ''}`} />
      {cfg.label}
    </Badge>
  )
}

function formatDuration(startedAt, completedAt) {
  if (!startedAt) return '\u2013'
  const start = new Date(startedAt)
  const end = completedAt ? new Date(completedAt) : new Date()
  const seconds = Math.round((end - start) / 1000)
  if (seconds < 60) return `${seconds}s`
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins}m ${secs.toString().padStart(2, '0')}s`
}

const MODEL_LABELS = {
  pretag: 'Pretag (label match)',
  structural: 'Structural inference',
  llm: 'LLM (Claude Sonnet)',
}

// ── Run List View ─────────────────────────────────────────

function RunListView({ onSelect, onNewRun }) {
  const { data: runs = [], isLoading } = useMachineTagRuns()

  if (isLoading) {
    return <div className="p-6 text-sm text-muted-foreground">Loading runs...</div>
  }

  return (
    <div className="flex flex-col gap-4 p-6 h-full overflow-y-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Machine Tag Runs</h1>
          <p className="text-sm text-muted-foreground">Run individual tagging models against datasets</p>
        </div>
        <Button onClick={onNewRun}>
          <Plus className="size-4 mr-1.5" />
          New Run
        </Button>
      </div>

      {runs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <Bot className="size-10 mb-3" />
          <p className="text-sm">No machine tag runs yet</p>
          <Button variant="outline" className="mt-3" onClick={onNewRun}>
            Start your first run
          </Button>
        </div>
      ) : (
        <div className="rounded-lg border overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Run ID</TableHead>
                <TableHead>Model</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Documents</TableHead>
                <TableHead>Progress</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.map(run => {
                const progress = run.progress || {}
                const pct = progress.docs_total
                  ? Math.round((progress.docs_completed / progress.docs_total) * 100)
                  : 0
                return (
                  <TableRow
                    key={run.run_id}
                    className="cursor-pointer"
                    onClick={() => onSelect(run.run_id)}
                  >
                    <TableCell className="font-mono text-sm">{run.run_id}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-[10px]">
                        {MODEL_LABELS[run.config?.model] || run.config?.model}
                      </Badge>
                    </TableCell>
                    <TableCell><StatusBadge status={run.status} /></TableCell>
                    <TableCell className="text-sm">
                      {progress.docs_completed ?? 0}/{progress.docs_total ?? '?'}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2 min-w-24">
                        <Progress value={pct} className="h-1.5 flex-1" />
                        <span className="text-xs text-muted-foreground w-8">{pct}%</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {formatDuration(run.started_at, run.completed_at)}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {run.created_at ? new Date(run.created_at).toLocaleDateString() : '\u2013'}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

// ── New Run Setup View ────────────────────────────────────

function NewRunView({ onBack, onCreated }) {
  const { data: documents = [] } = useDocuments()
  const { data: gtSets = [] } = useGTSets()
  const createRun = useCreateMachineTagRun()

  const [model, setModel] = useState('pretag')
  const [docMode, setDocMode] = useState('all')
  const [selectedDocs, setSelectedDocs] = useState([])
  const [gtSetId, setGtSetId] = useState('')
  const [docFilter, setDocFilter] = useState('')
  const [dryRun, setDryRun] = useState(false)
  const [verbose, setVerbose] = useState(false)

  // Output destinations
  const [writeTagLog, setWriteTagLog] = useState(true)
  const [writeVoting, setWriteVoting] = useState(false)

  const filteredDocs = useMemo(() => {
    const q = docFilter.toLowerCase()
    return documents.filter(d => !q || d.id.toLowerCase().includes(q))
  }, [documents, docFilter])

  const toggleDoc = (docId) => {
    setSelectedDocs(prev =>
      prev.includes(docId) ? prev.filter(d => d !== docId) : [...prev, docId]
    )
  }

  const resolvedDocs = docMode === 'all'
    ? documents.map(d => d.id)
    : docMode === 'select'
    ? selectedDocs
    : (() => {
        const set = gtSets.find(s => s.id === gtSetId)
        return set?.doc_ids || []
      })()

  const handleStart = () => {
    createRun.mutate({
      model,
      documents: resolvedDocs,
      config: {
        dry_run: dryRun,
        verbose,
        write_tag_log: writeTagLog,
        write_voting: writeVoting,
      },
    }, {
      onSuccess: (data) => {
        onCreated(data.run?.run_id)
      },
    })
  }

  return (
    <div className="flex flex-col gap-6 p-6 h-full overflow-y-auto max-w-3xl">
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={onBack}>
            <ArrowLeft className="size-4" />
          </Button>
          <h1 className="text-xl font-semibold">Configure Machine Tag Run</h1>
        </div>
        <p className="text-sm text-muted-foreground ml-11">
          Run a single tagging model against a dataset. Tags are written to table_graphs.json
          (native tagger behavior). Optionally send results to the tag log and/or voting system.
        </p>
      </div>

      {/* Model Selection */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Tagging Model</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="radio" checked={model === 'pretag'} onChange={() => setModel('pretag')} />
            Pretag (label match)
          </label>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="radio" checked={model === 'structural'} onChange={() => setModel('structural')} />
            Structural inference
          </label>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="radio" checked={model === 'llm'} onChange={() => setModel('llm')} />
            LLM (Claude Sonnet)
          </label>
        </CardContent>
      </Card>

      {/* Document Selection */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Documents</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="radio" checked={docMode === 'all'} onChange={() => setDocMode('all')} />
              All fixtures ({documents.length})
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="radio" checked={docMode === 'select'} onChange={() => setDocMode('select')} />
              Select...
            </label>
            {gtSets.length > 0 && (
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="radio" checked={docMode === 'gt'} onChange={() => setDocMode('gt')} />
                GT set
              </label>
            )}
          </div>
          {docMode === 'select' && (
            <div className="flex flex-col gap-2">
              <Input
                placeholder="Filter documents..."
                value={docFilter}
                onChange={e => setDocFilter(e.target.value)}
                className="max-w-sm"
              />
              <div className="border rounded-md max-h-40 overflow-y-auto p-2 flex flex-col gap-0.5">
                {filteredDocs.slice(0, 100).map(d => (
                  <label key={d.id} className="flex items-center gap-2 text-xs py-0.5 cursor-pointer hover:bg-muted px-1 rounded">
                    <input
                      type="checkbox"
                      checked={selectedDocs.includes(d.id)}
                      onChange={() => toggleDoc(d.id)}
                    />
                    <span className="truncate">{d.id}</span>
                    <Badge variant="outline" className="text-[9px] ml-auto shrink-0">{d.gaap}</Badge>
                  </label>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">{selectedDocs.length} selected</p>
            </div>
          )}
          {docMode === 'gt' && (
            <Select value={gtSetId} onValueChange={setGtSetId}>
              <SelectTrigger className="max-w-sm">
                <SelectValue placeholder="Select GT set..." />
              </SelectTrigger>
              <SelectContent>
                {gtSets.map(s => (
                  <SelectItem key={s.id} value={s.id}>{s.name} ({s.doc_count} docs)</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </CardContent>
      </Card>

      {/* Output Destinations */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Output Destinations</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <p className="text-xs text-muted-foreground">
            Tags always write to table_graphs.json. Select additional outputs below.
          </p>
          <div className="flex items-center gap-6 flex-wrap">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={writeTagLog} onChange={e => setWriteTagLog(e.target.checked)} />
              Tag log
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={writeVoting} onChange={e => setWriteVoting(e.target.checked)} />
              Voting / consensus
            </label>
          </div>
        </CardContent>
      </Card>

      {/* Options */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Options</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center gap-6 flex-wrap">
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" checked={dryRun} onChange={e => setDryRun(e.target.checked)} />
            Dry run (no writes)
          </label>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" checked={verbose} onChange={e => setVerbose(e.target.checked)} />
            Verbose logging
          </label>
        </CardContent>
      </Card>

      {/* Actions */}
      <div className="flex items-center gap-3 pb-4">
        <Button variant="outline" onClick={onBack}>Cancel</Button>
        <Button
          onClick={handleStart}
          disabled={createRun.isPending || (docMode === 'select' && selectedDocs.length === 0)}
        >
          {createRun.isPending ? (
            <><Loader2 className="size-4 mr-1.5 animate-spin" /> Starting...</>
          ) : (
            <><Play className="size-4 mr-1.5" /> Start Run</>
          )}
        </Button>
      </div>
    </div>
  )
}

// ── Run Detail View ───────────────────────────────────────

function RunDetailView({ runId, onBack }) {
  const { data: run } = useMachineTagRun(runId)
  const { data: results = [] } = useMachineTagRunResults(runId)
  const cancelRun = useCancelMachineTagRun()

  if (!run || run.error) {
    return <div className="p-6 text-sm text-muted-foreground">Run not found</div>
  }

  const progress = run.progress || {}
  const pct = progress.docs_total
    ? Math.round((progress.docs_completed / progress.docs_total) * 100)
    : 0
  const summary = run.summary || {}

  return (
    <div className="flex flex-col gap-4 p-6 h-full overflow-y-auto">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft className="size-4" />
        </Button>
        <h1 className="text-lg font-semibold font-mono">{run.run_id}</h1>
        <Badge variant="outline" className="text-[10px]">
          {MODEL_LABELS[run.config?.model] || run.config?.model}
        </Badge>
        <StatusBadge status={run.status} />
        <span className="text-sm text-muted-foreground">
          {progress.docs_completed ?? 0}/{progress.docs_total ?? '?'} docs
        </span>
        <span className="text-sm text-muted-foreground">
          {formatDuration(run.started_at, run.completed_at)}
        </span>
        {run.status === 'running' && (
          <Button
            variant="outline"
            size="sm"
            className="ml-auto text-destructive"
            onClick={() => cancelRun.mutate(runId)}
            disabled={cancelRun.isPending}
          >
            <Square className="size-3.5 mr-1" />
            Cancel
          </Button>
        )}
      </div>

      {/* Progress bar for running */}
      {run.status === 'running' && (
        <Progress value={pct} className="h-2" />
      )}

      {/* Summary cards */}
      {(run.status === 'completed' || run.status === 'failed') && summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {summary.docs_processed != null && (
            <Card>
              <CardContent className="pt-4 pb-3">
                <p className="text-2xl font-bold">{summary.docs_processed}</p>
                <p className="text-xs text-muted-foreground">Docs Processed</p>
              </CardContent>
            </Card>
          )}
          {summary.rows_tagged != null && (
            <Card>
              <CardContent className="pt-4 pb-3">
                <p className="text-2xl font-bold">{summary.rows_tagged?.toLocaleString()}</p>
                <p className="text-xs text-muted-foreground">Rows Tagged</p>
              </CardContent>
            </Card>
          )}
          {summary.tag_log_entries != null && (
            <Card>
              <CardContent className="pt-4 pb-3">
                <p className="text-2xl font-bold">{summary.tag_log_entries?.toLocaleString()}</p>
                <p className="text-xs text-muted-foreground">Tag Log Entries</p>
              </CardContent>
            </Card>
          )}
          {summary.votes_cast != null && (
            <Card>
              <CardContent className="pt-4 pb-3">
                <p className="text-2xl font-bold">{summary.votes_cast?.toLocaleString()}</p>
                <p className="text-xs text-muted-foreground">Votes Cast</p>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Config summary */}
      {run.config && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Configuration</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground flex gap-4 flex-wrap">
            <span>Model: <strong>{MODEL_LABELS[run.config.model] || run.config.model}</strong></span>
            {run.config.dry_run && <Badge variant="outline" className="text-[9px]">dry run</Badge>}
            {run.config.write_tag_log && <Badge variant="outline" className="text-[9px]">tag log</Badge>}
            {run.config.write_voting && <Badge variant="outline" className="text-[9px]">voting</Badge>}
          </CardContent>
        </Card>
      )}

      {/* Per-document results */}
      <div>
        <h2 className="font-semibold text-sm mb-2">Per-Document Results</h2>
        {results.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {run.status === 'running' ? 'Waiting for first document to complete...' : 'No results available'}
          </p>
        ) : (
          <div className="rounded-lg border overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Document</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Rows Tagged</TableHead>
                  <TableHead>Tag Log</TableHead>
                  <TableHead>Votes</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {results.map(r => (
                  <TableRow key={r.document_id}>
                    <TableCell className="font-medium text-sm">{r.document_id}</TableCell>
                    <TableCell>
                      {r.error ? (
                        <Badge variant="outline" className="text-[10px] bg-red-100 text-red-800">
                          error
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-[10px] bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400">
                          done
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-sm">{r.rows_tagged ?? '\u2013'}</TableCell>
                    <TableCell className="text-sm">{r.tag_log_entries ?? '\u2013'}</TableCell>
                    <TableCell className="text-sm">{r.votes_cast ?? '\u2013'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────

export default function MachineTagPage() {
  const [view, setView] = useState('list')
  const [activeRunId, setActiveRunId] = useState(null)

  switch (view) {
    case 'new':
      return (
        <NewRunView
          onBack={() => setView('list')}
          onCreated={(runId) => { setActiveRunId(runId); setView('detail') }}
        />
      )
    case 'detail':
      return (
        <RunDetailView
          runId={activeRunId}
          onBack={() => setView('list')}
        />
      )
    default:
      return (
        <RunListView
          onSelect={(runId) => { setActiveRunId(runId); setView('detail') }}
          onNewRun={() => setView('new')}
        />
      )
  }
}
