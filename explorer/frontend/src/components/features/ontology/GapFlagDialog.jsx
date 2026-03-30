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
import { useCreateGap, useOntologyContexts } from '@/api.js'

const CONTEXTS = [
  'FS.PNL', 'FS.SFP', 'FS.OCI', 'FS.CFS', 'FS.SOCIE',
  'DISC.PPE', 'DISC.INTANGIBLE', 'DISC.GOODWILL', 'DISC.INVESTMENT_PROPERTY',
  'DISC.LEASES', 'DISC.BORROWINGS', 'DISC.PROVISIONS', 'DISC.REVENUE',
  'DISC.TAX', 'DISC.EMPLOYEE_BENEFITS', 'DISC.SHARE_BASED_PAYMENTS',
  'DISC.FINANCIAL_INSTRUMENTS', 'DISC.FAIR_VALUE', 'DISC.SEGMENT',
  'DISC.RELATED_PARTIES', 'DISC.EARNINGS_PER_SHARE', 'DISC.DIVIDENDS',
  'DISC.CONTINGENCIES', 'DISC.EVENTS_AFTER_REPORTING', 'DISC.INVENTORIES',
  'DISC.RECEIVABLES', 'DISC.EQUITY',
]

export default function GapFlagDialog({ open, onOpenChange, prefill = {} }) {
  const [rowLabel, setRowLabel] = useState(prefill.row_label || '')
  const [context, setContext] = useState(prefill.context || '')
  const [description, setDescription] = useState('')
  const createGap = useCreateGap()

  const handleSubmit = () => {
    createGap.mutate({
      row_label: rowLabel,
      context: context || undefined,
      description: description || undefined,
      document_id: prefill.document_id,
      table_id: prefill.table_id,
      row_id: prefill.row_id,
    }, {
      onSuccess: () => {
        onOpenChange(false)
        setRowLabel('')
        setContext('')
        setDescription('')
      },
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Flag Ontology Gap</DialogTitle>
          <DialogDescription>
            Report a row label that doesn't map to any existing concept.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div>
            <label className="text-sm font-medium mb-1 block">Row Label</label>
            <Input
              value={rowLabel}
              onChange={e => setRowLabel(e.target.value)}
              placeholder="e.g. Revaluation surplus on property"
            />
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">Context</label>
            <Select value={context} onValueChange={setContext}>
              <SelectTrigger>
                <SelectValue placeholder="Select context..." />
              </SelectTrigger>
              <SelectContent>
                {CONTEXTS.map(c => (
                  <SelectItem key={c} value={c}>{c}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">Description (optional)</label>
            <textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="Why is this concept missing? What should it represent?"
              rows={3}
              className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={!rowLabel || createGap.isPending}>
            {createGap.isPending ? 'Submitting...' : 'Flag Gap'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
