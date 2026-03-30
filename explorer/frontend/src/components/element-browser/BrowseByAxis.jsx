import React from 'react'

export default function BrowseByAxis() {
  return (
    <div className="flex items-center justify-center h-full text-muted-foreground">
      <div className="text-center">
        <p className="text-lg font-medium text-foreground mb-2">Axis Browser</p>
        <p className="text-sm">Browse documents by dimensional axes (SEG, GEO, PPE).</p>
        <p className="text-sm mt-1">Requires /api/axes endpoints — coming in a future update.</p>
      </div>
    </div>
  )
}
