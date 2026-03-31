import { useState, useMemo } from 'react'
import { cn } from '@/lib/utils'
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from '../ui/collapsible.jsx'
import {
  ALL_SECTION_TYPES,
  DOCUMENT_TEMPLATE,
  TYPE_TO_GROUP,
  typeLabel,
} from '../section-hierarchy.js'
import { ChevronRight } from 'lucide-react'

/**
 * Pre-populated document structure tree.
 *
 * Shows the expected document template upfront with empty placeholders.
 * Nodes fill in with page ranges as transitions are marked.
 *
 * ● = transition found (filled)
 * ○ = expected, not yet found (placeholder)
 */
export function TransitionList({
  transitions,
  totalPages,
  selectedPage,
  onPageClick,
  onSuggestType,
}) {
  const sorted = useMemo(
    () => [...transitions].sort((a, b) => a.page - b.page),
    [transitions],
  )

  // Map: sectionType → transition (with computed endPage)
  const typeMap = useMemo(() => {
    const map = new Map()
    const withRanges = sorted.map((t, i) => ({
      ...t,
      endPage: i < sorted.length - 1 ? sorted[i + 1].page - 1 : totalPages,
    }))
    for (const t of withRanges) {
      // First transition of each type wins (for template matching)
      if (!map.has(t.section_type)) {
        map.set(t.section_type, t)
      }
    }
    return map
  }, [sorted, totalPages])

  // All types present in the template (for detecting "extra" transitions)
  const templateTypes = useMemo(() => {
    const set = new Set()
    for (const node of DOCUMENT_TEMPLATE) {
      if (node.kind === 'leaf') set.add(node.type)
      else {
        if (node.groupType) set.add(node.groupType)
        node.children.forEach(c => set.add(c))
      }
    }
    return set
  }, [])

  // Transitions not covered by the template (e.g., OTHER)
  const extraTransitions = useMemo(() => {
    const withRanges = sorted.map((t, i) => ({
      ...t,
      endPage: i < sorted.length - 1 ? sorted[i + 1].page - 1 : totalPages,
    }))
    return withRanges.filter(t => !templateTypes.has(t.section_type))
  }, [sorted, totalPages, templateTypes])

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Document Structure Tree */}
      <div className="flex-1 overflow-y-auto">
        <div className="px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Document Structure
        </div>

        {DOCUMENT_TEMPLATE.map(node =>
          node.kind === 'leaf' ? (
            <LeafRow
              key={node.type}
              type={node.type}
              transition={typeMap.get(node.type)}
              selectedPage={selectedPage}
              onPageClick={onPageClick}
              onSuggestType={onSuggestType}
              indent={0}
            />
          ) : (
            <GroupNode
              key={node.key}
              node={node}
              typeMap={typeMap}
              selectedPage={selectedPage}
              onPageClick={onPageClick}
              onSuggestType={onSuggestType}
            />
          )
        )}

        {/* Extra transitions not in template */}
        {extraTransitions.map(t => (
          <LeafRow
            key={`extra-${t.page}-${t.section_type}`}
            type={t.section_type}
            transition={t}
            selectedPage={selectedPage}
            onPageClick={onPageClick}
            onSuggestType={onSuggestType}
            indent={0}
          />
        ))}
      </div>

    </div>
  )
}

function GroupNode({ node, typeMap, selectedPage, onPageClick, onSuggestType }) {
  const [open, setOpen] = useState(true)

  // Group-level transition (e.g., GENERAL_REPORTING or PRIMARY_FINANCIALS)
  const groupTransition = node.groupType ? typeMap.get(node.groupType) : null
  const groupMeta = node.groupType ? ALL_SECTION_TYPES[node.groupType] : null

  // Compute aggregate range from filled children + group-level transition
  const { startPage, endPage, hasFilled } = useMemo(() => {
    let start = Infinity, end = -1, filled = false
    if (groupTransition) {
      filled = true
      start = Math.min(start, groupTransition.page)
      end = Math.max(end, groupTransition.endPage)
    }
    for (const childType of node.children) {
      const t = typeMap.get(childType)
      if (t) {
        filled = true
        start = Math.min(start, t.page)
        end = Math.max(end, t.endPage)
      }
    }
    return { startPage: start, endPage: end, hasFilled: filled }
  }, [node.children, typeMap, groupTransition])

  const isActive = hasFilled && selectedPage >= startPage && selectedPage <= endPage
  const isGroupSelected = groupTransition && selectedPage === groupTransition.page

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div
        className={cn(
          'flex items-center gap-1 w-full px-2 py-1 hover:bg-accent/50 rounded-sm',
          isActive && 'bg-accent/30',
          isGroupSelected && 'bg-accent',
        )}
      >
        <CollapsibleTrigger className="shrink-0 p-0.5 -ml-0.5">
          <ChevronRight
            className={cn(
              'size-3 transition-transform',
              hasFilled ? 'text-muted-foreground' : 'text-muted-foreground/40',
              open && 'rotate-90',
            )}
          />
        </CollapsibleTrigger>
        {/* Group dot — colored if group-level transition or any child filled */}
        {groupTransition || hasFilled ? (
          <span
            className="size-2 rounded-full shrink-0"
            style={{ backgroundColor: groupMeta?.hex || '#71717a' }}
          />
        ) : (
          <span className="size-2 rounded-full shrink-0 border border-muted-foreground/30" />
        )}
        <button
          className={cn(
            'text-[11px] font-medium truncate text-left',
            hasFilled ? 'text-muted-foreground' : 'text-muted-foreground/40',
          )}
          onClick={() => {
            if (groupTransition) {
              onPageClick(groupTransition.page)
            } else if (hasFilled) {
              onPageClick(startPage)
            } else if (node.groupType && onSuggestType) {
              onSuggestType(node.groupType)
            }
          }}
        >
          {node.label}
        </button>
        {hasFilled ? (
          <span className="text-[10px] tabular-nums text-muted-foreground/60 ml-auto shrink-0">
            {startPage}–{endPage}
          </span>
        ) : (
          <span className="text-[10px] text-muted-foreground/30 ml-auto shrink-0">—</span>
        )}
      </div>
      <CollapsibleContent>
        {node.children.map(childType => (
          <LeafRow
            key={childType}
            type={childType}
            transition={typeMap.get(childType)}
            selectedPage={selectedPage}
            onPageClick={onPageClick}
            onSuggestType={onSuggestType}
            indent={1}
          />
        ))}
      </CollapsibleContent>
    </Collapsible>
  )
}

function LeafRow({ type, transition, selectedPage, onPageClick, onSuggestType, indent = 0 }) {
  const meta = ALL_SECTION_TYPES[type]
  const isFilled = !!transition

  const isSelected = isFilled && transition.page === selectedPage
  const isInRange = isFilled && selectedPage >= transition.page && selectedPage <= transition.endPage

  const handleClick = () => {
    if (isFilled) {
      onPageClick(transition.page)
    } else if (onSuggestType) {
      onSuggestType(type)
    }
  }

  return (
    <button
      className={cn(
        'flex items-center gap-1.5 w-full py-1 text-left hover:bg-accent/50 rounded-sm',
        indent === 0 ? 'px-2' : 'px-2 pl-7',
        isInRange && !isSelected && 'bg-accent/25',
        isSelected && 'bg-accent',
      )}
      onClick={handleClick}
    >
      {/* Dot: colored if filled, grey ring if empty */}
      {isFilled ? (
        <span
          className="size-2 rounded-full shrink-0"
          style={{ backgroundColor: meta?.hex || '#71717a' }}
        />
      ) : (
        <span className="size-2 rounded-full shrink-0 border border-muted-foreground/30" />
      )}

      {/* Label */}
      <span className={cn(
        'text-xs truncate',
        !isFilled && 'text-muted-foreground/40',
      )}>
        {typeLabel(type)}
      </span>

      {/* Note number */}
      {isFilled && transition.note_number && (
        <span className="text-[10px] text-muted-foreground">
          n.{transition.note_number}
        </span>
      )}

      {/* Page range or dash */}
      {isFilled ? (
        <span className="text-[10px] tabular-nums text-muted-foreground/60 ml-auto shrink-0">
          {transition.page}–{transition.endPage}
        </span>
      ) : (
        <span className="text-[10px] text-muted-foreground/30 ml-auto shrink-0">—</span>
      )}

      {/* Provisional indicator */}
      {isFilled && !transition.validated && transition.source !== 'manual' && (
        <span
          className="size-1.5 rounded-full bg-yellow-500 shrink-0"
          title={`Provisional (${transition.source})`}
        />
      )}
    </button>
  )
}

