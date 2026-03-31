import React, { useState } from 'react'
import { useGTSets, useGTSetDocs, useCreateGTSet, useAddGTSetDocs, useDocuments } from '../api.js'
import { Button } from './ui/button.jsx'
import { Input } from './ui/input.jsx'
import {
  Card, CardHeader, CardTitle, CardDescription, CardFooter
} from './ui/card.jsx'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from './ui/dialog.jsx'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell
} from './ui/table.jsx'
import { Plus, ArrowLeft, Search } from 'lucide-react'
import { PdfIndicator } from './ui/pdf-indicator.jsx'
import { Textarea } from './ui/textarea.jsx'
import { Skeleton } from './ui/skeleton.jsx'

// ── New Set Dialog ─────────────────────────────────────

function NewSetDialog({ open, onOpenChange }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const createSet = useCreateGTSet()

  const handleCreate = () => {
    createSet.mutate({ name, description }, {
      onSuccess: () => {
        setName('')
        setDescription('')
        onOpenChange(false)
      },
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New Ground Truth Set</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <Input placeholder="Set name (e.g. FOBE100)" value={name} onChange={e => setName(e.target.value)} />
          <Textarea
            placeholder="Description..."
            value={description}
            onChange={e => setDescription(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleCreate} disabled={!name.trim() || createSet.isPending}>Create</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Add Docs Dialog ────────────────────────────────────

function AddDocsDialog({ open, onOpenChange, setId, existingDocIds }) {
  const { data: documents = [] } = useDocuments()
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState(new Set())
  const addDocs = useAddGTSetDocs(setId)

  const existingSet = new Set(existingDocIds)
  const filtered = documents.filter(d =>
    !existingSet.has(d.id) &&
    (d.id.toLowerCase().includes(search.toLowerCase()) ||
     (d.name || '').toLowerCase().includes(search.toLowerCase()))
  )

  const toggleDoc = (docId) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(docId)) next.delete(docId)
      else next.add(docId)
      return next
    })
  }

  const handleAdd = () => {
    addDocs.mutate([...selected], {
      onSuccess: () => {
        setSelected(new Set())
        onOpenChange(false)
      },
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Add Documents</DialogTitle>
        </DialogHeader>
        <div className="relative mb-2">
          <Search className="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground" />
          <Input
            placeholder="Search documents..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="pl-8"
          />
        </div>
        <div className="flex-1 overflow-y-auto border rounded-md max-h-72">
          {filtered.map(doc => (
            <label
              key={doc.id}
              className="flex items-center gap-2 px-3 py-2 hover:bg-muted cursor-pointer text-sm border-b last:border-b-0"
            >
              <input
                type="checkbox"
                checked={selected.has(doc.id)}
                onChange={() => toggleDoc(doc.id)}
                className="rounded"
              />
              <span className="truncate flex-1">{doc.id}</span>
              {doc.name && doc.name !== doc.id && (
                <span className="text-xs text-muted-foreground truncate max-w-32">{doc.name}</span>
              )}
            </label>
          ))}
          {filtered.length === 0 && (
            <div className="p-4 text-sm text-muted-foreground text-center">No documents available</div>
          )}
        </div>
        <DialogFooter>
          <span className="text-xs text-muted-foreground mr-auto">{selected.size} selected</span>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleAdd} disabled={selected.size === 0 || addDocs.isPending}>
            Add {selected.size} Document{selected.size !== 1 ? 's' : ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Set Detail View ────────────────────────────────────

function SetDetail({ set, onBack }) {
  const { data: docs = [], isLoading } = useGTSetDocs(set.id)
  const [addDialogOpen, setAddDialogOpen] = useState(false)

  const existingDocIds = docs.map(d => d.slug)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon-sm" onClick={onBack}>
          <ArrowLeft className="size-4" />
        </Button>
        <div>
          <h2 className="text-lg font-semibold">{set.name}</h2>
          {set.description && <p className="text-sm text-muted-foreground">{set.description}</p>}
        </div>
        <span className="text-sm text-muted-foreground tabular-nums">{docs.length} docs</span>
        <Button size="sm" className="ml-auto" onClick={() => setAddDialogOpen(true)}>
          <Plus className="size-3.5 mr-1" /> Add Docs
        </Button>
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
        </div>
      ) : docs.length === 0 ? (
        <div className="text-sm text-muted-foreground text-center py-8">
          No documents in this set yet. Click "Add Docs" to get started.
        </div>
      ) : (
        <div className="rounded-lg border overflow-hidden">
          <Table>
            <TableHeader className="bg-muted sticky top-0 z-10">
              <TableRow>
                <TableHead>Document</TableHead>
                <TableHead className="text-right">Pages</TableHead>
                <TableHead>PDF</TableHead>
                <TableHead className="text-right">Size</TableHead>
                <TableHead className="text-right">Texts</TableHead>
                <TableHead className="text-right">Tables</TableHead>
                <TableHead className="text-right">DL pgs</TableHead>
                <TableHead className="text-right">TG pgs</TableHead>
                <TableHead>Match</TableHead>
                <TableHead className="text-right">Tags</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {docs.map(doc => (
                <TableRow key={doc.document_id}>
                  <TableCell>
                    <div className="font-medium text-sm">{doc.slug}</div>
                    {doc.entity_name && (
                      <div className="text-[11px] text-muted-foreground">{doc.entity_name}</div>
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {doc.page_count || '\u2013'}
                  </TableCell>
                  <TableCell>
                    <PdfIndicator hasPdf={doc.has_pdf} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground text-xs">
                    {doc.docling_size != null ? (
                      doc.docling_url ? (
                        <a href={doc.docling_url} target="_blank" rel="noopener noreferrer"
                           className="text-blue-500 hover:underline">{doc.docling_size}KB</a>
                      ) : `${doc.docling_size}KB`
                    ) : '\u2013'}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground text-xs">
                    {doc.docling_texts ?? '\u2013'}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground text-xs">
                    {doc.docling_tables ?? '\u2013'}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground text-xs">
                    {doc.docling_pages ?? '\u2013'}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground text-xs">
                    {doc.tg_pages ?? '\u2013'}
                  </TableCell>
                  <TableCell>
                    {doc.docling_match === 'ok' ? (
                      <span className="text-xs font-medium text-green-600">OK</span>
                    ) : doc.docling_match === 'partial' ? (
                      <span className="text-xs font-medium text-amber-600">Partial</span>
                    ) : doc.docling_match === 'missing' ? (
                      <span className="text-xs font-medium text-red-500">Missing</span>
                    ) : doc.docling_match === 'error' ? (
                      <span className="text-xs font-medium text-red-500">Error</span>
                    ) : (
                      <span className="text-xs text-muted-foreground">{'\u2013'}</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-xs">
                    {doc.tag_coverage != null ? (
                      <span className={
                        doc.tag_coverage === 100 ? 'font-medium text-green-600' :
                        doc.tag_coverage > 0 ? 'font-medium text-amber-600' :
                        'text-muted-foreground'
                      }>
                        {doc.tag_coverage}%
                      </span>
                    ) : (
                      <span className="text-muted-foreground">{'\u2013'}</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <AddDocsDialog
        open={addDialogOpen}
        onOpenChange={setAddDialogOpen}
        setId={set.id}
        existingDocIds={existingDocIds}
      />
    </div>
  )
}

// ── Main Page ──────────────────────────────────────────

export default function GroundTruthPage() {
  const { data: sets = [], isLoading } = useGTSets()
  const [newDialogOpen, setNewDialogOpen] = useState(false)
  const [activeSet, setActiveSet] = useState(null)

  if (activeSet) {
    return (
      <div className="px-4 lg:px-6 py-6 md:py-8 overflow-y-auto h-full">
        <SetDetail set={activeSet} onBack={() => setActiveSet(null)} />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6 px-4 lg:px-6 py-6 md:py-8 overflow-y-auto h-full">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Ground Truth Sets</h1>
          <p className="text-sm text-muted-foreground">Curated document collections for evaluation</p>
        </div>
        <Button onClick={() => setNewDialogOpen(true)}>
          <Plus className="size-3.5 mr-1" /> New Set
        </Button>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-32 w-full rounded-xl" />)}
        </div>
      ) : sets.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <p className="text-lg font-medium text-foreground mb-2">No ground truth sets</p>
          <p className="text-sm">Create your first set to start curating evaluation documents.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {sets.map(set => (
            <Card
              key={set.id}
              className="cursor-pointer hover:border-primary/50 transition-colors"
              onClick={() => setActiveSet(set)}
            >
              <CardHeader>
                <CardTitle className="text-base">{set.name}</CardTitle>
                {set.description && (
                  <CardDescription className="line-clamp-2">{set.description}</CardDescription>
                )}
              </CardHeader>
              <CardFooter>
                <span className="text-sm text-muted-foreground">{set.doc_count} document{set.doc_count !== 1 ? 's' : ''}</span>
              </CardFooter>
            </Card>
          ))}
        </div>
      )}

      <NewSetDialog open={newDialogOpen} onOpenChange={setNewDialogOpen} />
    </div>
  )
}
