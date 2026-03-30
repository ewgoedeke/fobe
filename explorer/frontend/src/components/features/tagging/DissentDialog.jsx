import React, { useState } from 'react'
import { useCastVote } from '@/api.js'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
  DialogDescription, DialogFooter,
} from '@/components/ui/dialog.jsx'
import { Button } from '@/components/ui/button.jsx'
import { Input } from '@/components/ui/input.jsx'
import { Textarea } from '@/components/ui/textarea.jsx'

/**
 * Dialog for submitting a dissent vote.
 * Props: dimension, targetId, currentValue, open, onOpenChange
 */
export default function DissentDialog({ dimension, targetId, currentValue, open, onOpenChange }) {
  const [value, setValue] = useState('')
  const [comment, setComment] = useState('')
  const castVote = useCastVote()

  const handleSubmit = () => {
    castVote.mutate({
      dimension,
      target_id: targetId,
      action: 'dissent',
      value: value || null,
      prev_value: currentValue,
      source: 'human',
      comment: comment || null,
    }, {
      onSuccess: () => {
        setValue('')
        setComment('')
        onOpenChange(false)
      },
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Disagree with tag</DialogTitle>
          <DialogDescription>
            Current value: <span className="font-mono font-medium">{currentValue || 'none'}</span>
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div>
            <label className="text-sm font-medium mb-1 block">What should this be?</label>
            <Input
              placeholder="Concept ID or value..."
              value={value}
              onChange={e => setValue(e.target.value)}
            />
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">Why?</label>
            <Textarea
              placeholder="Reason for disagreement..."
              value={comment}
              onChange={e => setComment(e.target.value)}
              className="min-h-[80px]"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={castVote.isPending}>
            {castVote.isPending ? 'Submitting...' : 'Submit Dissent'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
