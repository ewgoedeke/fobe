import { useState } from 'react'
import { cn } from '@/lib/utils'
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from '../ui/collapsible.jsx'
import {
  ALL_SECTION_TYPES,
  SECTION_GROUPS,
  typeLabel,
} from '../section-hierarchy.js'
import { ChevronRight } from 'lucide-react'

/**
 * Collapsible tree showing hierarchy groups with colored dots and page ranges.
 * Click a section to navigate to its start page.
 */
export function HierarchyOutline({ groups, selectedPage, onPageClick }) {
  const [expanded, setExpanded] = useState(() => {
    const init = {}
    groups.forEach((_, i) => { init[i] = true })
    return init
  })

  if (groups.length === 0) {
    return (
      <div className="p-3 text-xs text-muted-foreground">
        No transitions marked yet. Select a page and mark a transition to begin.
      </div>
    )
  }

  return (
    <div className="py-1 overflow-y-auto h-full">
      {groups.map((group, gi) => {
        const groupDef = SECTION_GROUPS[group.groupKey]
        const groupLabel = groupDef?.label || group.groupKey

        return (
          <Collapsible
            key={gi}
            open={expanded[gi] !== false}
            onOpenChange={(open) => setExpanded(prev => ({ ...prev, [gi]: open }))}
          >
            <CollapsibleTrigger className="flex items-center gap-1.5 w-full px-2 py-1 hover:bg-accent/50 rounded-sm cursor-pointer">
              <ChevronRight
                className={cn(
                  'size-3 text-muted-foreground transition-transform shrink-0',
                  expanded[gi] !== false && 'rotate-90',
                )}
              />
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground truncate">
                {groupLabel}
              </span>
              <span className="text-[11px] text-muted-foreground tabular-nums ml-auto shrink-0">
                {group.startPage}–{group.endPage}
              </span>
            </CollapsibleTrigger>

            <CollapsibleContent>
              <div className="ml-3 border-l border-border">
                {group.sections.map((sec, si) => {
                  const typeMeta = ALL_SECTION_TYPES[sec.type]
                  const isActive = selectedPage >= sec.startPage && selectedPage <= sec.endPage
                  const displayLabel = sec.noteNumber
                    ? `n.${sec.noteNumber}${sec.label ? ` ${sec.label}` : ''}`
                    : (sec.label || typeLabel(sec.type))

                  return (
                    <button
                      key={si}
                      className={cn(
                        'flex items-center gap-1.5 w-full px-2 py-0.5 text-left hover:bg-accent/50 rounded-sm',
                        isActive && 'bg-accent',
                      )}
                      onClick={() => onPageClick(sec.startPage)}
                    >
                      <span
                        className="size-2 rounded-full shrink-0"
                        style={{ backgroundColor: typeMeta?.hex || '#71717a' }}
                      />
                      <span className="text-xs truncate">{displayLabel}</span>
                      {!sec.validated && sec.source !== 'manual' && (
                        <span className="size-1.5 rounded-full bg-yellow-500 shrink-0" title="Provisional" />
                      )}
                      <span className="text-[11px] text-muted-foreground tabular-nums ml-auto shrink-0">
                        {sec.startPage === sec.endPage
                          ? sec.startPage
                          : `${sec.startPage}–${sec.endPage}`}
                      </span>
                    </button>
                  )
                })}
              </div>
            </CollapsibleContent>
          </Collapsible>
        )
      })}
    </div>
  )
}
