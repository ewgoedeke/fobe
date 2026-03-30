import React, { useState } from 'react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog.jsx'
import { Button } from '@/components/ui/button.jsx'
import { Input } from '@/components/ui/input.jsx'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select.jsx'
import { useCreateProposal } from '@/api.js'

export default function ProposeConceptDialog({ open, onOpenChange, gap = null }) {
  const [conceptId, setConceptId] = useState(gap?.context ? `${gap.context}.` : '')
  const [label, setLabel] = useState(gap?.row_label || '')
  const [context, setContext] = useState(gap?.context || '')
  const [balanceType, setBalanceType] = useState('')
  const [periodType, setPeriodType] = useState('duration')
  const [unitType, setUnitType] = useState('monetary')
  const [gaap, setGaap] = useState('')
  const [rationale, setRationale] = useState('')

  const createProposal = useCreateProposal()

  const handleSubmit = () => {
    createProposal.mutate({
      gap_id: gap?.id,
      concept_id: conceptId,
      label,
      context: context || undefined,
      balance_type: balanceType || undefined,
      period_type: periodType || undefined,
      unit_type: unitType || undefined,
      gaap: gaap || undefined,
      rationale: rationale || undefined,
      example_docs: gap?.document_id ? [gap.document_id] : [],
    }, {
      onSuccess: () => {
        onOpenChange(false)
      },
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Propose New Concept</DialogTitle>
          <DialogDescription>
            {gap ? `Filling gap: "${gap.row_label}"` : 'Propose a new concept for the ontology.'}
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3 max-h-[60vh] overflow-y-auto">
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className="text-sm font-medium mb-1 block">Concept ID</label>
              <Input
                value={conceptId}
                onChange={e => setConceptId(e.target.value)}
                placeholder="e.g. DISC.PPE.REVALUATION_SURPLUS"
                className="font-mono text-sm"
              />
            </div>
            <div className="col-span-2">
              <label className="text-sm font-medium mb-1 block">Label</label>
              <Input
                value={label}
                onChange={e => setLabel(e.target.value)}
                placeholder="e.g. Revaluation surplus"
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Context</label>
              <Input
                value={context}
                onChange={e => setContext(e.target.value)}
                placeholder="e.g. DISC.PPE"
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">GAAP</label>
              <Select value={gaap} onValueChange={setGaap}>
                <SelectTrigger>
                  <SelectValue placeholder="All (universal)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All (universal)</SelectItem>
                  <SelectItem value="IFRS">IFRS</SelectItem>
                  <SelectItem value="UGB">UGB</SelectItem>
                  <SelectItem value="HGB">HGB</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Balance Type</label>
              <Select value={balanceType} onValueChange={setBalanceType}>
                <SelectTrigger>
                  <SelectValue placeholder="None" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  <SelectItem value="debit">Debit</SelectItem>
                  <SelectItem value="credit">Credit</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Period Type</label>
              <Select value={periodType} onValueChange={setPeriodType}>
                <SelectTrigger>
                  <SelectValue placeholder="Duration" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="duration">Duration</SelectItem>
                  <SelectItem value="instant">Instant</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">Rationale</label>
            <textarea
              value={rationale}
              onChange={e => setRationale(e.target.value)}
              placeholder="Why should this concept be added to the ontology?"
              rows={3}
              className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            onClick={handleSubmit}
            disabled={!conceptId || !label || createProposal.isPending}
          >
            {createProposal.isPending ? 'Submitting...' : 'Propose Concept'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
