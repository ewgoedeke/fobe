import React, { useState, useMemo } from 'react'
import {
  useRuns, useRun, useRunResults, useRunDefaults, useCreateRun, useCancelRun,
  useDocuments, useGTSets, useGTSetDocs,
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
  AlertTriangle, Clock, Loader2, RefreshCw,
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

// ── Run List View ─────────────────────────────────────────

function RunListView({ onSelect, onNewRun }) {
  const { data: runs = [], isLoading } = useRuns()

  if (isLoading) {
    return <div className="p-6 text-sm text-muted-foreground">Loading runs...</div>
  }

  return (
    <div className="flex flex-col gap-4 p-6 h-full overflow-y-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Training Runs</h1>
          <p className="text-sm text-muted-foreground">Pipeline execution history and results</p>
        </div>
        <Button onClick={onNewRun}>
          <Plus className="size-4 mr-1.5" />
          New Run
        </Button>
      </div>

      {runs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <Play className="size-10 mb-3" />
          <p className="text-sm">No pipeline runs yet</p>
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

const ALL_STAGES = [
  { id: 'stage1', label: '1 - Load' },
  { id: 'stage2', label: '2 - Classify' },
  { id: 'stage3', label: '3 - Numeric' },
  { id: 'stage4', label: '4 - Structure' },
  { id: 'stage5', label: '5 - Tagging' },
  { id: 'stage6', label: '6 - Validation' },
]

function NewRunView({ onBack, onCreated }) {
  const { data: documents = [] } = useDocuments()
  const { data: gtSets = [] } = useGTSets()
  const { data: defaults } = useRunDefaults()
  const createRun = useCreateRun()
  // GT set doc resolution is handled via the file-based .gt_sets.json which stores doc_ids directly

  const [docMode, setDocMode] = useState('all')  // all | select | gt
  const [selectedDocs, setSelectedDocs] = useState([])
  const [gtSetId, setGtSetId] = useState('')
  const [docFilter, setDocFilter] = useState('')
  const [stages, setStages] = useState(new Set(['stage1', 'stage2', 'stage3', 'stage4', 'stage5', 'stage6']))
  const [useLlm, setUseLlm] = useState(true)
  const [reclassify, setReclassify] = useState(false)
  const [useGroundTruth, setUseGroundTruth] = useState(false)
  const [gaapFilter, setGaapFilter] = useState('all')

  // Training config
  const [runMode, setRunMode] = useState('pretag')  // pretag | train
  const [evalSplit, setEvalSplit] = useState(20)     // % held out for eval
  const [model, setModel] = useState('lightgbm')
  const [iterations, setIterations] = useState(500)

  // Thresholds
  const dt = defaults?.thresholds || {}
  const [minDistinct, setMinDistinct] = useState(dt.stage2?.min_distinct_statements ?? 1)
  const [maxPerType, setMaxPerType] = useState(dt.stage2?.max_per_primary_type ?? 8)
  const [minParseRate, setMinParseRate] = useState(dt.stage3?.min_parse_rate ?? 0.60)
  const [minConsistency, setMinConsistency] = useState(dt.stage4?.min_consistency_rate ?? 0.50)
  const [minTagRate, setMinTagRate] = useState(dt.stage5?.min_tag_rate ?? 0.10)

  const toggleStage = (id) => {
    const next = new Set(stages)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setStages(next)
  }

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
        // Resolve docs from GT set - sets contain doc_ids from file-based storage
        const set = gtSets.find(s => s.id === gtSetId)
        return set?.doc_ids || []
      })()

  const handleStart = () => {
    createRun.mutate({
      documents: resolvedDocs,
      stages: [...stages].sort(),
      mode: runMode,
      config: {
        use_llm: useLlm,
        reclassify,
        use_ground_truth: useGroundTruth,
        gaap_filter: gaapFilter === 'all' ? null : gaapFilter,
        thresholds: {
          stage2: { min_distinct_statements: Number(minDistinct), max_per_primary_type: Number(maxPerType) },
          stage3: { min_parse_rate: Number(minParseRate) },
          stage4: { min_consistency_rate: Number(minConsistency) },
          stage5: { min_tag_rate: Number(minTagRate) },
        },
        ...(runMode === 'train' && {
          training: {
            eval_split: Number(evalSplit) / 100,
            model,
            iterations: Number(iterations),
          },
        }),
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
          <h1 className="text-xl font-semibold">Configure Pipeline Run</h1>
        </div>
        <p className="text-sm text-muted-foreground ml-11">
          Pretags documents by running each through a 6-stage pipeline: classify tables by statement type,
          parse numerics, infer row hierarchy, and tag rows with ontology concepts via label matching,
          structural propagation, and optional LLM inference. The resulting tags serve as training data
          for the tagging model.
        </p>
      </div>

      {/* Mode */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Mode</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="radio" checked={runMode === 'pretag'} onChange={() => setRunMode('pretag')} />
            Pretag only
          </label>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="radio" checked={runMode === 'train'} onChange={() => setRunMode('train')} />
            Train model
          </label>
        </CardContent>
      </Card>

      {/* Training Config */}
      {runMode === 'train' && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Training Configuration</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-x-6 gap-y-3 max-w-xl">
              <div>
                <label className="text-xs text-muted-foreground">Model</label>
                <Select value={model} onValueChange={setModel}>
                  <SelectTrigger className="h-8 mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="lightgbm">LightGBM</SelectItem>
                    <SelectItem value="xgboost">XGBoost</SelectItem>
                    <SelectItem value="catboost">CatBoost</SelectItem>
                    <SelectItem value="random_forest">Random Forest</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-xs text-muted-foreground">Eval split (%)</label>
                <Input type="number" min={5} max={50} step={5} value={evalSplit} onChange={e => setEvalSplit(e.target.value)} className="h-8 mt-1" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground">Iterations</label>
                <Input type="number" min={50} max={10000} step={50} value={iterations} onChange={e => setIterations(e.target.value)} className="h-8 mt-1" />
              </div>
            </div>
          </CardContent>
        </Card>
      )}

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

      {/* Stages */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Stages</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4 flex-wrap">
            {ALL_STAGES.map(s => (
              <label key={s.id} className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={stages.has(s.id)}
                  onChange={() => toggleStage(s.id)}
                />
                {s.label}
              </label>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Options */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Options</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex items-center gap-6 flex-wrap">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={useLlm} onChange={e => setUseLlm(e.target.checked)} />
              Use LLM tagging
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={reclassify} onChange={e => setReclassify(e.target.checked)} />
              Reclassify from scratch
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={useGroundTruth} onChange={e => setUseGroundTruth(e.target.checked)} />
              Use ground truth TOC
            </label>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm">GAAP:</span>
            <Select value={gaapFilter} onValueChange={setGaapFilter}>
              <SelectTrigger className="w-28">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="IFRS">IFRS</SelectItem>
                <SelectItem value="UGB">UGB</SelectItem>
                <SelectItem value="HGB">HGB</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Gate Thresholds */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Gate Thresholds</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-x-6 gap-y-3 max-w-lg">
            <div>
              <label className="text-xs text-muted-foreground">Stage 2 — Min primary types</label>
              <Input type="number" value={minDistinct} onChange={e => setMinDistinct(e.target.value)} className="h-8 mt-1" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Stage 2 — Max per type</label>
              <Input type="number" value={maxPerType} onChange={e => setMaxPerType(e.target.value)} className="h-8 mt-1" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Stage 3 — Min parse rate</label>
              <Input type="number" step="0.05" value={minParseRate} onChange={e => setMinParseRate(e.target.value)} className="h-8 mt-1" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Stage 4 — Min consistency</label>
              <Input type="number" step="0.05" value={minConsistency} onChange={e => setMinConsistency(e.target.value)} className="h-8 mt-1" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Stage 5 — Min tag rate</label>
              <Input type="number" step="0.05" value={minTagRate} onChange={e => setMinTagRate(e.target.value)} className="h-8 mt-1" />
            </div>
          </div>
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
  const { data: run } = useRun(runId)
  const { data: results = [] } = useRunResults(runId)
  const cancelRun = useCancelRun()

  if (!run || run.error) {
    return <div className="p-6 text-sm text-muted-foreground">Run not found</div>
  }

  const progress = run.progress || {}
  const pct = progress.docs_total
    ? Math.round((progress.docs_completed / progress.docs_total) * 100)
    : 0
  const summary = run.summary || {}

  const haltedDocs = results.filter(r => r.halted_at)

  return (
    <div className="flex flex-col gap-4 p-6 h-full overflow-y-auto">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft className="size-4" />
        </Button>
        <h1 className="text-lg font-semibold font-mono">{run.run_id}</h1>
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
          {summary.total_tables != null && (
            <Card>
              <CardContent className="pt-4 pb-3">
                <p className="text-2xl font-bold">{summary.total_tables?.toLocaleString()}</p>
                <p className="text-xs text-muted-foreground">Tables</p>
              </CardContent>
            </Card>
          )}
          {summary.total_data_rows != null && (
            <Card>
              <CardContent className="pt-4 pb-3">
                <p className="text-2xl font-bold">{summary.total_data_rows?.toLocaleString()}</p>
                <p className="text-xs text-muted-foreground">Data Rows</p>
              </CardContent>
            </Card>
          )}
          {summary.total_pretagged != null && (
            <Card>
              <CardContent className="pt-4 pb-3">
                <p className="text-2xl font-bold">{summary.total_pretagged?.toLocaleString()}</p>
                <p className="text-xs text-muted-foreground">Tagged</p>
              </CardContent>
            </Card>
          )}
          {summary.total_facts != null && (
            <Card>
              <CardContent className="pt-4 pb-3">
                <p className="text-2xl font-bold">{summary.total_facts?.toLocaleString()}</p>
                <p className="text-xs text-muted-foreground">Facts</p>
              </CardContent>
            </Card>
          )}
        </div>
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
                  <TableHead>Halted At</TableHead>
                  <TableHead>Tables</TableHead>
                  <TableHead>Tag Rate</TableHead>
                  <TableHead>Facts</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {results.map(r => {
                  const m = r.metrics || {}
                  return (
                    <TableRow key={r.document_id}>
                      <TableCell className="font-medium text-sm">{r.document_id}</TableCell>
                      <TableCell>
                        {r.halted_at ? (
                          <Badge variant="outline" className="text-[10px] bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400">
                            halted
                          </Badge>
                        ) : r.error ? (
                          <Badge variant="outline" className="text-[10px] bg-red-100 text-red-800">
                            error
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="text-[10px] bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400">
                            done
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {r.halted_at || '\u2013'}
                      </TableCell>
                      <TableCell className="text-sm">{m.tables ?? '\u2013'}</TableCell>
                      <TableCell className="text-sm">
                        {m.tag_rate != null ? `${(m.tag_rate * 100).toFixed(1)}%` : '\u2013'}
                      </TableCell>
                      <TableCell className="text-sm">{m.indexed_facts ?? '\u2013'}</TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      {/* Re-run halted button */}
      {haltedDocs.length > 0 && run.status !== 'running' && (
        <div className="flex items-center gap-2">
          <AlertTriangle className="size-4 text-amber-500" />
          <span className="text-sm text-muted-foreground">{haltedDocs.length} docs halted at gate</span>
          <Button variant="outline" size="sm">
            <RefreshCw className="size-3.5 mr-1" />
            Re-run Halted
          </Button>
        </div>
      )}
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────

export default function TrainingPage() {
  const [view, setView] = useState('list')  // list | new | detail
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
