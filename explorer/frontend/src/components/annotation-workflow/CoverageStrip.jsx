import { ALL_SECTION_TYPES } from '../section-hierarchy.js'
import { cn } from '@/lib/utils'

/**
 * 20px tall interactive page bar showing section coverage.
 * One colored div per page, click to select.
 * Multi-tagged pages show horizontal color stripes.
 * TOC suggestion markers shown as sky-blue top borders.
 * ML predictions shown as faint colors on untagged pages.
 */
export function CoverageStrip({ totalPages, pageMap, selectedPage, onPageClick, tocEntryPages, resolvedMultiTags = new Map() }) {
  if (!totalPages || totalPages <= 0) return null

  return (
    <div className="h-5 flex w-full rounded-sm overflow-hidden border border-border bg-muted/50">
      {Array.from({ length: totalPages }, (_, i) => {
        const page = i + 1
        const info = pageMap.get(page)
        const typeMeta = info ? ALL_SECTION_TYPES[info.type] : null
        const isSelected = page === selectedPage
        const isTocSuggestion = tocEntryPages?.has(page)
        const pageMulti = resolvedMultiTags.get(page) || []

        // ML predictions are only used for tag suggestions, not shown in coverage strip

        // Collect all colors for this page (primary + multi-tags)
        const colors = []
        if (typeMeta) colors.push(typeMeta.hex)
        for (const mt of pageMulti) {
          const mtMeta = ALL_SECTION_TYPES[mt]
          if (mtMeta && mtMeta.hex !== typeMeta?.hex) colors.push(mtMeta.hex)
        }

        const isMultiColored = colors.length > 1
        const primaryOpacity = typeMeta
          ? (info.source === 'manual' || info.validated ? 0.8 : 0.45)
          : 0.15

        const titleParts = [`p.${page}`]
        if (info) titleParts.push(info.type)
        for (const mt of pageMulti) titleParts.push(`+${mt}`)
        if (isTocSuggestion) titleParts.push('(TOC)')

        return (
          <div
            key={page}
            className={cn(
              'flex-1 min-w-0 cursor-pointer transition-opacity hover:opacity-80 relative overflow-hidden',
              isSelected && 'ring-1 ring-foreground ring-inset',
            )}
            style={isMultiColored ? {} : {
              backgroundColor: typeMeta ? typeMeta.hex : 'transparent',
              opacity: primaryOpacity,
            }}
            onClick={() => onPageClick(page)}
            title={titleParts.join(' — ')}
          >
            {/* Multi-color horizontal stripes */}
            {isMultiColored && colors.map((color, ci) => (
              <div
                key={ci}
                className="absolute inset-x-0"
                style={{
                  backgroundColor: color,
                  opacity: primaryOpacity,
                  top: `${(ci / colors.length) * 100}%`,
                  height: `${100 / colors.length}%`,
                }}
              />
            ))}
            {isTocSuggestion && (
              <div className="absolute inset-x-0 top-0 h-[3px] bg-sky-400 z-10" style={{ opacity: 0.9 }} />
            )}
          </div>
        )
      })}
    </div>
  )
}
