import { ALL_SECTION_TYPES } from '../section-hierarchy.js'
import { cn } from '@/lib/utils'

/**
 * 12px tall interactive page bar showing section coverage.
 * One colored div per page, click to select.
 */
export function CoverageStrip({ totalPages, pageMap, selectedPage, onPageClick }) {
  if (!totalPages || totalPages <= 0) return null

  return (
    <div className="h-3 flex w-full rounded-sm overflow-hidden border border-border bg-muted/50">
      {Array.from({ length: totalPages }, (_, i) => {
        const page = i + 1
        const info = pageMap.get(page)
        const typeMeta = info ? ALL_SECTION_TYPES[info.type] : null
        const isSelected = page === selectedPage

        return (
          <div
            key={page}
            className={cn(
              'flex-1 min-w-0 cursor-pointer transition-opacity hover:opacity-80',
              isSelected && 'ring-1 ring-foreground ring-inset',
            )}
            style={{
              backgroundColor: typeMeta ? typeMeta.hex : 'transparent',
              opacity: typeMeta ? (info.source === 'manual' || info.validated ? 0.8 : 0.45) : 0.15,
            }}
            onClick={() => onPageClick(page)}
            title={`p.${page}${info ? ` — ${info.type}` : ''}`}
          />
        )
      })}
    </div>
  )
}
