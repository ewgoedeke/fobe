import React, { useState, useMemo } from 'react'
import {
  useDocuments, useDocEdges, useAutoDetectEdges, useValidateEdge, useDeleteEdge,
} from '../api.js'
import { Badge } from './ui/badge.jsx'
import { Button } from './ui/button.jsx'
import { Input } from './ui/input.jsx'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from './ui/select.jsx'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from './ui/table.jsx'
import {
  Search, Zap, Check, Trash2, ChevronRight,
} from 'lucide-react'
import { PdfIndicator } from './ui/pdf-indicator.jsx'
import { Skeleton } from './ui/skeleton.jsx'

const EDGE_TYPE_LABELS = {
  note_ref: 'Note Ref',
  toc_to_section: 'TOC \u2192 Section',
  cross_statement: 'Cross-Statement',
}

const EDGE_TYPE_COLORS = {
  note_ref: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  toc_to_section: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400',
  cross_statement: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
}

// ── Edge List ──────────────────────────────────────────

function EdgeList({ edges, activeEdgeId, onSelect, onValidate, onDelete }) {
  const grouped = useMemo(() => {
    const groups = {}
    for (const e of edges) {
      const type = e.edge_type || 'unknown'
      if (!groups[type]) groups[type] = []
      groups[type].push(e)
    }
    return groups
  }, [edges])

  if (edges.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted-foreground p-4">
        No edges detected. Click "Auto-detect" to scan for references.
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {Object.entries(grouped).map(([type, typeEdges]) => (
        <div key={type}>
          <div className="px-3 py-2 bg-muted/50 border-b sticky top-0 z-10">
            <div className="flex items-center gap-2">
              <Badge variant="outline" className={`text-[10px] ${EDGE_TYPE_COLORS[type] || ''}`}>
                {EDGE_TYPE_LABELS[type] || type}
              </Badge>
              <span className="text-xs text-muted-foreground">{typeEdges.length}</span>
            </div>
          </div>
          {typeEdges.map(edge => {
            const isActive = edge.id === activeEdgeId
            return (
              <div
                key={edge.id}
                className={`px-3 py-2 border-b cursor-pointer text-sm transition-colors flex items-center gap-2
                  ${isActive ? 'bg-accent' : 'hover:bg-muted/50'}`}
                onClick={() => onSelect(edge)}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="truncate font-medium">
                      {edge.source_label || edge.source_id}
                    </span>
                    <ChevronRight className="size-3 text-muted-foreground shrink-0" />
                    <span className="truncate text-muted-foreground">
                      {edge.target_context || edge.target_id}
                    </span>
                  </div>
                  {edge.note_number && (
                    <span className="text-[10px] text-muted-foreground">Note {edge.note_number}</span>
                  )}
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  {edge.validated ? (
                    <Badge variant="outline" className="text-[10px] bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
                      Validated
                    </Badge>
                  ) : (
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      title="Validate"
                      onClick={(e) => { e.stopPropagation(); onValidate(edge.id) }}
                    >
                      <Check className="size-3" />
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    title="Delete"
                    onClick={(e) => { e.stopPropagation(); onDelete(edge.id) }}
                    className="text-destructive hover:text-destructive"
                  >
                    <Trash2 className="size-3" />
                  </Button>
                </div>
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}

// ── Edge Detail Panel ──────────────────────────────────

function EdgeDetail({ edge }) {
  if (!edge) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
        Select an edge to view details
      </div>
    )
  }

  return (
    <div className="p-4 overflow-y-auto">
      <h3 className="font-semibold mb-3">Edge Detail</h3>
      <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
        <div>
          <span className="text-muted-foreground text-xs">Type</span>
          <p>
            <Badge variant="outline" className={`text-[10px] ${EDGE_TYPE_COLORS[edge.edge_type] || ''}`}>
              {EDGE_TYPE_LABELS[edge.edge_type] || edge.edge_type}
            </Badge>
          </p>
        </div>
        <div>
          <span className="text-muted-foreground text-xs">Note Number</span>
          <p className="font-medium">{edge.note_number ?? '\u2013'}</p>
        </div>
        <div>
          <span className="text-muted-foreground text-xs">Source</span>
          <p className="font-mono text-xs">{edge.source_type}: {edge.source_id}</p>
          {edge.source_label && <p className="text-xs text-muted-foreground">{edge.source_label}</p>}
          {edge.source_context && <Badge variant="outline" className="text-[10px] mt-0.5">{edge.source_context}</Badge>}
        </div>
        <div>
          <span className="text-muted-foreground text-xs">Target</span>
          <p className="font-mono text-xs">{edge.target_type}: {edge.target_id}</p>
          {edge.target_context && <Badge variant="outline" className="text-[10px] mt-0.5">{edge.target_context}</Badge>}
        </div>
        <div>
          <span className="text-muted-foreground text-xs">Confidence</span>
          <p className="font-medium">{edge.confidence != null ? `${(edge.confidence * 100).toFixed(0)}%` : '\u2013'}</p>
        </div>
        <div>
          <span className="text-muted-foreground text-xs">Validated</span>
          <p className="font-medium">{edge.validated ? 'Yes' : 'No'}</p>
        </div>
      </div>
    </div>
  )
}

// ── Main Page ──────────────────────────────────────────

export default function DocumentEdgesPage() {
  const { data: documents = [] } = useDocuments()
  const [selectedDocId, setSelectedDocId] = useState(null)
  const [activeEdge, setActiveEdge] = useState(null)
  const [docFilter, setDocFilter] = useState('')

  const { data: edges = [], isLoading } = useDocEdges(selectedDocId)
  const autoDetect = useAutoDetectEdges(selectedDocId)
  const validateEdge = useValidateEdge(selectedDocId)
  const deleteEdge = useDeleteEdge(selectedDocId)

  const filteredDocs = useMemo(() => {
    const q = docFilter.toLowerCase()
    return documents.filter(d => !q || d.id.toLowerCase().includes(q) || (d.name || '').toLowerCase().includes(q))
  }, [documents, docFilter])

  const handleValidate = (edgeId) => {
    validateEdge.mutate({ edgeId, updates: { validated: true } })
  }

  const handleDelete = (edgeId) => {
    deleteEdge.mutate(edgeId)
    if (activeEdge?.id === edgeId) setActiveEdge(null)
  }

  const [autoDetectError, setAutoDetectError] = useState(null)

  const handleAutoDetect = () => {
    setAutoDetectError(null)
    autoDetect.mutate(undefined, {
      onError: (err) => setAutoDetectError(err.message),
      onSuccess: () => setAutoDetectError(null),
    })
  }

  // Grouped counts for the summary
  const edgeCounts = useMemo(() => {
    const counts = {}
    for (const e of edges) {
      counts[e.edge_type] = (counts[e.edge_type] || 0) + 1
    }
    return counts
  }, [edges])

  const validatedCount = edges.filter(e => e.validated).length

  if (!selectedDocId) {
    // Document selection view
    return (
      <div className="flex flex-col gap-4 px-4 lg:px-6 py-6 md:py-8 overflow-y-auto h-full">
        <div>
          <h1 className="text-xl font-semibold">Document Edges</h1>
          <p className="text-sm text-muted-foreground">Cross-references, TOC links, and note mappings</p>
        </div>
        <div className="relative max-w-md">
          <Search className="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground" />
          <Input
            placeholder="Search documents..."
            value={docFilter}
            onChange={e => setDocFilter(e.target.value)}
            className="pl-8"
          />
        </div>
        <div className="rounded-lg border overflow-hidden">
          <Table>
            <TableHeader className="bg-muted sticky top-0 z-10">
              <TableRow>
                <TableHead>Document</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>PDF</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredDocs.slice(0, 50).map(doc => (
                <TableRow
                  key={doc.id}
                  className="cursor-pointer"
                  onClick={() => { setSelectedDocId(doc.id); setActiveEdge(null); setAutoDetectError(null) }}
                >
                  <TableCell className="font-medium text-sm">{doc.id}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{doc.name !== doc.id ? doc.name : '\u2013'}</TableCell>
                  <TableCell>
                    <PdfIndicator hasPdf={doc.has_pdf} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        {filteredDocs.length > 50 && (
          <p className="text-xs text-muted-foreground">Showing 50 of {filteredDocs.length}. Filter to narrow.</p>
        )}
      </div>
    )
  }

  // Edge browser view
  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-2 border-b shrink-0">
        <Button variant="ghost" size="sm" onClick={() => { setSelectedDocId(null); setActiveEdge(null); setAutoDetectError(null) }}>
          \u2190 Back
        </Button>
        <h2 className="font-semibold text-sm">{selectedDocId}</h2>
        <div className="flex items-center gap-2 ml-2">
          {Object.entries(edgeCounts).map(([type, count]) => (
            <Badge key={type} variant="outline" className={`text-[10px] ${EDGE_TYPE_COLORS[type] || ''}`}>
              {EDGE_TYPE_LABELS[type] || type}: {count}
            </Badge>
          ))}
          {edges.length > 0 && (
            <span className="text-xs text-muted-foreground">
              {validatedCount}/{edges.length} validated
            </span>
          )}
        </div>
        <div className="ml-auto">
          <Button
            size="sm"
            variant="outline"
            onClick={handleAutoDetect}
            disabled={autoDetect.isPending}
          >
            <Zap className="size-3.5 mr-1" />
            {autoDetect.isPending ? 'Detecting...' : 'Auto-detect'}
          </Button>
        </div>
      </div>

      {/* Error banner */}
      {autoDetectError && (
        <div className="mx-4 mt-2 px-3 py-2 rounded-md bg-destructive/10 text-destructive text-sm border border-destructive/20">
          {autoDetectError}
        </div>
      )}

      {/* Main content: edge list + detail */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Edge list */}
        <div className="w-96 shrink-0 border-r overflow-hidden">
          {isLoading ? (
            <div className="p-4 flex flex-col gap-2">
              {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
            </div>
          ) : (
            <EdgeList
              edges={edges}
              activeEdgeId={activeEdge?.id}
              onSelect={setActiveEdge}
              onValidate={handleValidate}
              onDelete={handleDelete}
            />
          )}
        </div>

        {/* Right: Edge detail */}
        <div className="flex-1 overflow-hidden">
          <EdgeDetail edge={activeEdge} />
        </div>
      </div>
    </div>
  )
}
