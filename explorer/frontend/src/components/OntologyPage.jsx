import React, { useState, useMemo } from 'react'
import { useOntologyContexts, useOntologyContextTree, useOntologyConceptDetail, useOntologyGaps, useConceptProposals } from '../api.js'
import { Badge } from './ui/badge.jsx'
import { Button } from './ui/button.jsx'
import { Input } from './ui/input.jsx'
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs.jsx'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from './ui/collapsible.jsx'
import GapFlagDialog from './features/ontology/GapFlagDialog.jsx'
import GapsList from './features/ontology/GapsList.jsx'
import ProposalsList from './features/ontology/ProposalsList.jsx'
import ProposeConceptDialog from './features/ontology/ProposeConceptDialog.jsx'
import {
  ChevronRight, ChevronDown, Star, Link2, Search, Plus,
} from 'lucide-react'

// ── Left panel: Context selector ───────────────────────

function ContextSelector({ contexts, activeContext, onSelect }) {
  const primary = contexts.filter(c => c.group === 'primary')
  const disclosure = contexts.filter(c => c.group === 'disclosure')

  const CtxItem = ({ ctx }) => (
    <button
      onClick={() => onSelect(ctx.id)}
      className={`w-full text-left px-3 py-2 rounded-md text-sm flex items-center justify-between transition-colors
        ${activeContext === ctx.id
          ? 'bg-primary text-primary-foreground'
          : 'hover:bg-muted'}`}
    >
      <span className="truncate font-medium">{ctx.id}</span>
      <Badge variant="secondary" className="ml-2 text-[10px] shrink-0">{ctx.concept_count}</Badge>
    </button>
  )

  return (
    <div className="flex flex-col gap-4 p-3 overflow-y-auto h-full">
      <div>
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2 px-1">
          Primary Statements
        </h3>
        <div className="flex flex-col gap-0.5">
          {primary.map(ctx => <CtxItem key={ctx.id} ctx={ctx} />)}
        </div>
      </div>
      <div>
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2 px-1">
          Disclosures
        </h3>
        <div className="flex flex-col gap-0.5">
          {disclosure.map(ctx => <CtxItem key={ctx.id} ctx={ctx} />)}
        </div>
      </div>
    </div>
  )
}

// ── Middle panel: Concept tree ─────────────────────────

function ConceptTreeNode({ node, depth = 0, activeConcept, onSelect, filter }) {
  const [open, setOpen] = useState(depth < 1)

  const matchesFilter = !filter ||
    node.label.toLowerCase().includes(filter) ||
    node.id.toLowerCase().includes(filter)
  const hasMatchingChild = node.children?.some(c => nodeMatchesFilter(c, filter))

  if (filter && !matchesFilter && !hasMatchingChild) return null

  const hasChildren = node.children?.length > 0
  const isActive = activeConcept === node.id

  return (
    <div>
      <div
        className={`flex items-center gap-1 py-1 px-2 rounded-md cursor-pointer text-sm transition-colors
          ${isActive ? 'bg-accent text-accent-foreground' : 'hover:bg-muted'}`}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={() => onSelect(node.id)}
      >
        {hasChildren ? (
          <button
            onClick={(e) => { e.stopPropagation(); setOpen(!open) }}
            className="shrink-0 p-0.5 rounded hover:bg-muted-foreground/10"
          >
            {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
          </button>
        ) : (
          <span className="w-4.5" />
        )}
        <span className="truncate flex-1">{node.label}</span>
        {node.is_total && <Star className="size-3 text-amber-500 shrink-0" />}
        {node.edge_count > 2 && <Link2 className="size-3 text-muted-foreground shrink-0" />}
      </div>
      {hasChildren && open && (
        <div>
          {node.children.map(child => (
            <ConceptTreeNode
              key={child.id}
              node={child}
              depth={depth + 1}
              activeConcept={activeConcept}
              onSelect={onSelect}
              filter={filter}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function nodeMatchesFilter(node, filter) {
  if (!filter) return true
  if (node.label.toLowerCase().includes(filter) || node.id.toLowerCase().includes(filter)) return true
  return node.children?.some(c => nodeMatchesFilter(c, filter)) ?? false
}

function ConceptTree({ contextId, activeConcept, onSelect }) {
  const { data, isLoading } = useOntologyContextTree(contextId)
  const [filter, setFilter] = useState('')

  const filterLower = filter.toLowerCase()

  if (!contextId) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
        Select a context to browse concepts
      </div>
    )
  }

  if (isLoading) {
    return <div className="p-4 text-sm text-muted-foreground">Loading...</div>
  }

  const tree = data?.tree || []

  return (
    <div className="flex flex-col h-full">
      <div className="p-2 border-b">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground" />
          <Input
            placeholder="Filter concepts..."
            value={filter}
            onChange={e => setFilter(e.target.value)}
            className="pl-8 h-8 text-sm"
          />
        </div>
        <div className="text-xs text-muted-foreground mt-1 px-1">
          {data?.concept_count || 0} concepts
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-1">
        {tree.map(node => (
          <ConceptTreeNode
            key={node.id}
            node={node}
            activeConcept={activeConcept}
            onSelect={onSelect}
            filter={filterLower}
          />
        ))}
      </div>
    </div>
  )
}

// ── Right panel: Concept detail ────────────────────────

function ConceptDetail({ conceptId }) {
  const { data, isLoading } = useOntologyConceptDetail(conceptId)

  if (!conceptId) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
        Select a concept for details
      </div>
    )
  }

  if (isLoading) return <div className="p-4 text-sm text-muted-foreground">Loading...</div>
  if (!data || data.error) return <div className="p-4 text-sm text-destructive">Concept not found</div>

  const crossEdges = data.cross_edges || []
  const examples = data.examples || []

  // Deduplicate cross edges by concept_id + edge_type
  const uniqueEdges = []
  const seen = new Set()
  for (const e of crossEdges) {
    const key = `${e.concept_id}:${e.edge_type}`
    if (!seen.has(key)) {
      seen.add(key)
      uniqueEdges.push(e)
    }
  }

  return (
    <div className="p-4 overflow-y-auto h-full flex flex-col gap-4">
      <div>
        <h3 className="font-semibold text-lg">{data.label}</h3>
        <p className="text-xs text-muted-foreground font-mono mt-0.5">{data.id}</p>
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
        <div>
          <span className="text-muted-foreground">Context</span>
          <p className="font-medium">{data.context}</p>
        </div>
        <div>
          <span className="text-muted-foreground">Balance</span>
          <p className="font-medium">{data.balance_type || '\u2013'}</p>
        </div>
        <div>
          <span className="text-muted-foreground">Unit</span>
          <p className="font-medium">{data.unit_type || '\u2013'}</p>
        </div>
        <div>
          <span className="text-muted-foreground">Is Total</span>
          <p className="font-medium">{data.is_total ? 'Yes' : 'No'}</p>
        </div>
      </div>

      {uniqueEdges.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold mb-2">Cross-Context Links ({uniqueEdges.length})</h4>
          <div className="flex flex-col gap-1 max-h-48 overflow-y-auto">
            {uniqueEdges.map((e, i) => (
              <div key={i} className="flex items-center gap-2 text-xs py-1 px-2 rounded bg-muted/50">
                <Badge variant="outline" className="text-[10px] shrink-0">{e.edge_type}</Badge>
                <span className="truncate">{e.label}</span>
                <span className="text-muted-foreground shrink-0">{e.context}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {examples.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold mb-2">Tagged Examples ({examples.length})</h4>
          <div className="flex flex-col gap-1 max-h-64 overflow-y-auto">
            {examples.map((ex, i) => (
              <div key={i} className="text-xs py-1.5 px-2 rounded bg-muted/50 flex items-center gap-2">
                <span className="font-medium truncate flex-1">{ex.row_label || '\u2013'}</span>
                <Badge variant="outline" className="text-[10px] shrink-0">{ex.tag_source}</Badge>
                <span className="text-muted-foreground shrink-0">{ex.doc_id}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main page ──────────────────────────────────────────

// ── Browse tab content ─────────────────────────────────

function BrowseTab() {
  const { data: contexts = [] } = useOntologyContexts()
  const [activeContext, setActiveContext] = useState(null)
  const [activeConcept, setActiveConcept] = useState(null)

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 px-4 py-2 border-b text-sm">
        <span className="font-medium">Ontology</span>
        {activeContext && (
          <>
            <ChevronRight className="size-3 text-muted-foreground" />
            <button
              className="font-medium hover:underline"
              onClick={() => setActiveConcept(null)}
            >
              {activeContext}
            </button>
          </>
        )}
        {activeConcept && (
          <>
            <ChevronRight className="size-3 text-muted-foreground" />
            <span className="text-muted-foreground truncate max-w-64">{activeConcept}</span>
          </>
        )}
      </div>

      {/* Three panels */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Context selector */}
        <div className="w-56 shrink-0 border-r overflow-hidden">
          <ContextSelector
            contexts={contexts}
            activeContext={activeContext}
            onSelect={(ctx) => { setActiveContext(ctx); setActiveConcept(null) }}
          />
        </div>

        {/* Middle: Concept tree */}
        <div className="flex-1 min-w-0 border-r overflow-hidden">
          <ConceptTree
            contextId={activeContext}
            activeConcept={activeConcept}
            onSelect={setActiveConcept}
          />
        </div>

        {/* Right: Concept detail */}
        <div className="w-80 shrink-0 overflow-hidden">
          <ConceptDetail conceptId={activeConcept} />
        </div>
      </div>
    </div>
  )
}

// ── Gaps tab content ──────────────────────────────────

function GapsTab() {
  const [gapFlagOpen, setGapFlagOpen] = useState(false)
  const [proposeGap, setProposeGap] = useState(null)

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 border-b">
        <div>
          <h2 className="font-semibold text-sm">Ontology Gaps</h2>
          <p className="text-xs text-muted-foreground">Row labels that don't map to existing concepts</p>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => setGapFlagOpen(true)}>
            <Plus className="size-3.5 mr-1" />
            Flag Gap
          </Button>
        </div>
      </div>
      <div className="flex-1 overflow-hidden">
        <GapsList onSelectGap={(gap) => setProposeGap(gap)} />
      </div>
      <GapFlagDialog open={gapFlagOpen} onOpenChange={setGapFlagOpen} />
      {proposeGap && (
        <ProposeConceptDialog
          open={!!proposeGap}
          onOpenChange={(open) => { if (!open) setProposeGap(null) }}
          gap={proposeGap}
        />
      )}
    </div>
  )
}

// ── Proposals tab content ──────────────────────────────

function ProposalsTab() {
  const [selectedProposal, setSelectedProposal] = useState(null)

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 border-b">
        <div>
          <h2 className="font-semibold text-sm">Concept Proposals</h2>
          <p className="text-xs text-muted-foreground">Proposed new concepts to fill ontology gaps</p>
        </div>
      </div>
      <div className="flex-1 overflow-hidden">
        <ProposalsList onSelectProposal={setSelectedProposal} />
      </div>
    </div>
  )
}

// ── Main page ──────────────────────────────────────────

export default function OntologyPage() {
  const { data: gaps = [] } = useOntologyGaps()
  const { data: proposals = [] } = useConceptProposals()

  const openGapCount = gaps.filter(g => g.status === 'open').length
  const pendingProposalCount = proposals.filter(p => p.status === 'draft' || p.status === 'review').length

  return (
    <Tabs defaultValue="browse" className="flex flex-col h-full overflow-hidden">
      <div className="border-b px-4">
        <TabsList className="h-9">
          <TabsTrigger value="browse" className="text-sm">Browse</TabsTrigger>
          <TabsTrigger value="gaps" className="text-sm gap-1.5">
            Gaps
            {openGapCount > 0 && (
              <Badge variant="secondary" className="text-[10px] h-4 px-1 ml-1">{openGapCount}</Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="proposals" className="text-sm gap-1.5">
            Proposals
            {pendingProposalCount > 0 && (
              <Badge variant="secondary" className="text-[10px] h-4 px-1 ml-1">{pendingProposalCount}</Badge>
            )}
          </TabsTrigger>
        </TabsList>
      </div>
      <TabsContent value="browse" className="flex-1 overflow-hidden mt-0">
        <BrowseTab />
      </TabsContent>
      <TabsContent value="gaps" className="flex-1 overflow-hidden mt-0">
        <GapsTab />
      </TabsContent>
      <TabsContent value="proposals" className="flex-1 overflow-hidden mt-0">
        <ProposalsTab />
      </TabsContent>
    </Tabs>
  )
}
