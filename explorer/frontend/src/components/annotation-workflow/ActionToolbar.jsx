import { useState, useEffect, useMemo } from 'react'
import { cn } from '@/lib/utils'
import { Button } from '../ui/button.jsx'
import { Input } from '../ui/input.jsx'
import { Badge } from '../ui/badge.jsx'
import {
  ALL_SECTION_TYPES,
  TYPE_TO_GROUP,
  typeLabel,
} from '../section-hierarchy.js'
import { Trash2, ArrowLeftRight, X, Check, Plus } from 'lucide-react'

// Broad categories for row 1
const CATEGORIES = [
  { key: 'FRONT_MATTER', short: 'FM', label: 'Front Matter', types: [] },
  { key: 'TOC', short: 'TOC', label: 'TOC', types: [] },
  {
    key: 'GENERAL_REPORTING', short: 'GEN', label: 'General Reporting',
    types: [
      'MANAGEMENT_REPORT', 'ESG', 'CORPORATE_GOVERNANCE',
      'RISK_REPORT', 'REMUNERATION_REPORT', 'SUPERVISORY_BOARD',
      'AUDITOR_REPORT', 'RESPONSIBILITY_STATEMENT',
    ],
  },
  {
    key: 'PRIMARY_FINANCIALS', short: 'AFS', label: 'Primary Financials',
    types: ['PNL', 'SFP', 'OCI', 'CFS', 'SOCIE'],
  },
  {
    key: 'NOTES', short: 'NOTES', label: 'Notes',
    types: [
      'NOTES_GENERAL', 'NOTES_PPE', 'NOTES_INTANGIBLES',
      'NOTES_FIN_INST', 'NOTES_TAX', 'NOTES_REVENUE',
      'NOTES_PERSONNEL', 'NOTES_PROVISIONS', 'NOTES_LEASES',
      'NOTES_SEGMENT', 'NOTES_RELATED_PARTIES', 'NOTES_OTHER',
    ],
  },
  { key: 'APPENDIX', short: 'APPX', label: 'Appendix', types: [] },
]

/**
 * Two-row action toolbar for marking transitions.
 * Row 1: broad category buttons (FM, TOC, GEN, AFS, NOTES, APPX)
 * Row 2: specific sub-types for the selected category
 */
export function ActionToolbar({
  selectedPage,
  totalPages,
  currentTransition,
  pageInfo,
  suggestedType,
  onAddTransition,
  onRemoveTransition,
  multiTags = [],
  resolvedMultiTags = new Map(),
  onToggleMultiTag,
  onCompareClick,
  hasEdges = false,
}) {
  const [noteNumber, setNoteNumber] = useState('')
  const [activeCategory, setActiveCategory] = useState(null)
  const [tagMenuExpanded, setTagMenuExpanded] = useState(true)

  // Derive active category from current transition or suggestion
  useEffect(() => {
    const type = currentTransition?.section_type || suggestedType || ''
    if (!type) {
      setActiveCategory(null)
      setNoteNumber('')
      setTagMenuExpanded(true)
      return
    }
    // Find which category this type belongs to
    const cat = CATEGORIES.find(c => c.key === type)
    if (cat) {
      setActiveCategory(cat.key)
    } else {
      // It's a sub-type — find its parent category
      const parent = CATEGORIES.find(c => c.types.includes(type))
      setActiveCategory(parent?.key || null)
    }
    setNoteNumber(currentTransition?.note_number || '')
    setTagMenuExpanded(false)
  }, [selectedPage, currentTransition, suggestedType])

  // The active category object
  const activeCat = useMemo(
    () => CATEGORIES.find(c => c.key === activeCategory) || null,
    [activeCategory],
  )

  // Current tagged type for this page
  const currentType = currentTransition?.section_type || null

  // If page already has a primary tag and menu was opened via "+ Add Tag",
  // add as multi-tag instead of replacing the primary tag
  const tagOrMultiTag = (type) => {
    if (currentTransition && currentTransition.section_type !== type) {
      onToggleMultiTag?.(selectedPage, type)
      setTagMenuExpanded(false)
    } else {
      onAddTransition({
        page: selectedPage,
        section_type: type,
        label: '',
        note_number: noteNumber || null,
        source: 'manual',
        validated: true,
      })
    }
  }

  // Whether clicks should add multi-tags (menu expanded on already-tagged page)
  const addingMultiTag = tagMenuExpanded && !!currentTransition

  const handleCategoryClick = (cat) => {
    if (cat.types.length === 0) {
      // Leaf category — tag directly (or multi-tag)
      if (addingMultiTag) {
        tagOrMultiTag(cat.key)
      } else {
        onAddTransition({
          page: selectedPage,
          section_type: cat.key,
          label: '',
          note_number: null,
          source: 'manual',
          validated: true,
        })
      }
      setActiveCategory(cat.key)
    } else {
      // Group category — expand sub-types row, tag at group level
      if (activeCategory === cat.key) {
        // Already selected — tag at group level
        if (addingMultiTag) {
          tagOrMultiTag(cat.key)
        } else {
          onAddTransition({
            page: selectedPage,
            section_type: cat.key,
            label: '',
            note_number: null,
            source: 'manual',
            validated: true,
          })
        }
      } else {
        setActiveCategory(cat.key)
      }
    }
  }

  const handleSubTypeClick = (type) => {
    if (addingMultiTag) {
      tagOrMultiTag(type)
    } else {
      onAddTransition({
        page: selectedPage,
        section_type: type,
        label: '',
        note_number: noteNumber || null,
        source: 'manual',
        validated: true,
      })
    }
  }

  // Use resolved (carry-forward) multi-tags for display
  const resolvedTypes = resolvedMultiTags.get(selectedPage) || []
  const pageMultiTags = resolvedTypes.map(st => ({ page: selectedPage, section_type: st }))

  return (
    <div className="border-b border-border shrink-0">
      {/* Row 1: broad categories + actions */}
      <div className="flex items-center gap-1 px-3 py-1 h-8">
        {currentTransition && !tagMenuExpanded ? (
          <>
            {/* Collapsed: show current tag chip + multi-tag chips + Add Tag */}
            <button
              className="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold hover:opacity-80"
              style={{
                backgroundColor: `${ALL_SECTION_TYPES[currentType]?.hex}22`,
                color: ALL_SECTION_TYPES[currentType]?.hex,
              }}
              onClick={() => {
                onRemoveTransition(selectedPage)
                setActiveCategory(null)
                setNoteNumber('')
              }}
              title="Remove tag"
            >
              <span className="size-2 rounded-full shrink-0"
                style={{ backgroundColor: ALL_SECTION_TYPES[currentType]?.hex }} />
              {typeLabel(currentType)}
              <X className="size-3" />
            </button>

            {pageMultiTags.map(mt => {
              const meta = ALL_SECTION_TYPES[mt.section_type]
              return (
                <Badge
                  key={mt.section_type}
                  variant="secondary"
                  className={cn('text-[10px] px-1.5 py-0 gap-0.5 cursor-pointer h-5', meta?.bg, meta?.text)}
                  onClick={() => onToggleMultiTag?.(selectedPage, mt.section_type)}
                >
                  {typeLabel(mt.section_type)}
                  <X className="size-2.5" />
                </Badge>
              )
            })}

            <Button
              variant="outline"
              size="sm"
              className="h-5 text-[10px] px-2 ml-1"
              onClick={() => setTagMenuExpanded(true)}
            >
              <Plus className="size-3" />
              Add Tag
            </Button>
          </>
        ) : (
          <>
            {/* Current tag chip (shown before categories when adding multi-tag) */}
            {currentTransition && (
              <button
                className="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold hover:opacity-80 shrink-0"
                style={{
                  backgroundColor: `${ALL_SECTION_TYPES[currentType]?.hex}22`,
                  color: ALL_SECTION_TYPES[currentType]?.hex,
                }}
                onClick={() => {
                  onRemoveTransition(selectedPage)
                  setActiveCategory(null)
                  setNoteNumber('')
                }}
                title="Remove tag"
              >
                <span className="size-2 rounded-full shrink-0"
                  style={{ backgroundColor: ALL_SECTION_TYPES[currentType]?.hex }} />
                {typeLabel(currentType)}
                <X className="size-3" />
              </button>
            )}

            {pageMultiTags.map(mt => {
              const meta = ALL_SECTION_TYPES[mt.section_type]
              return (
                <Badge
                  key={`top-${mt.section_type}`}
                  variant="secondary"
                  className={cn('text-[10px] px-1.5 py-0 gap-0.5 cursor-pointer h-5 shrink-0', meta?.bg, meta?.text)}
                  onClick={() => onToggleMultiTag?.(selectedPage, mt.section_type)}
                >
                  {typeLabel(mt.section_type)}
                  <X className="size-2.5" />
                </Badge>
              )
            })}

            {(currentTransition || pageMultiTags.length > 0) && (
              <div className="w-px h-4 bg-border shrink-0" />
            )}

            {/* Expanded: full category buttons */}
            {CATEGORIES.map(cat => {
              const meta = ALL_SECTION_TYPES[cat.key]
              const isActive = activeCategory === cat.key
              const isTagged = currentType === cat.key
              // Also highlight if current type is a sub-type of this category
              const hasTaggedChild = cat.types.includes(currentType)

              return (
                <button
                  key={cat.key}
                  className={cn(
                    'flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium transition-colors',
                    isActive
                      ? 'bg-accent ring-1 ring-primary/30'
                      : 'hover:bg-accent/50',
                    (isTagged || hasTaggedChild) && !isActive && 'bg-accent/30',
                  )}
                  onClick={() => handleCategoryClick(cat)}
                  title={cat.label}
                >
                  <span
                    className="size-2 rounded-full shrink-0"
                    style={{ backgroundColor: meta?.hex || '#71717a' }}
                  />
                  <span className={cn(
                    isActive || isTagged || hasTaggedChild
                      ? 'text-foreground'
                      : 'text-muted-foreground',
                  )}>
                    {cat.short}
                  </span>
                  {isTagged && <Check className="size-3 text-primary" />}
                </button>
              )
            })}

            {/* Note number */}
            {(activeCategory === 'NOTES' || activeCategory === 'PRIMARY_FINANCIALS') && (
              <Input
                className="h-6 w-14 text-xs tabular-nums ml-1"
                placeholder="n.#"
                value={noteNumber}
                onChange={e => setNoteNumber(e.target.value)}
              />
            )}

            {/* Cancel button when adding multi-tags */}
            {addingMultiTag && (
              <Button
                variant="ghost"
                size="sm"
                className="h-5 text-[10px] px-1.5 ml-1"
                onClick={() => setTagMenuExpanded(false)}
              >
                <X className="size-3" />
              </Button>
            )}
          </>
        )}

        {/* Spacer */}
        <div className="flex-1" />

        {/* Page info */}
        <span className="text-[11px] text-muted-foreground tabular-nums shrink-0">
          p.{selectedPage}/{totalPages}
          {currentTransition && (
            <>
              {' \u00b7 '}
              <span style={{ color: ALL_SECTION_TYPES[currentType]?.hex }}>
                {typeLabel(currentType)}
              </span>
              {currentTransition.note_number && ` n.${currentTransition.note_number}`}
            </>
          )}
        </span>

        {/* Compare */}
        {hasEdges && (
          <Button
            variant="outline"
            size="sm"
            className="h-6 text-xs gap-1 ml-1"
            onClick={onCompareClick}
          >
            <ArrowLeftRight className="size-3" />
            Cmp
          </Button>
        )}
      </div>

      {/* Row 2: sub-types for active category (only when menu is expanded) */}
      {tagMenuExpanded && activeCat && activeCat.types.length > 0 && (
        <div className="flex items-center gap-1 px-3 py-0.5 h-7 border-t border-border/50 bg-muted/30">
          {/* Group-level option */}
          <button
            className={cn(
              'flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] transition-colors',
              currentType === activeCat.key
                ? 'bg-accent font-medium'
                : 'hover:bg-accent/50 text-muted-foreground',
            )}
            onClick={() => handleSubTypeClick(activeCat.key)}
            title={`Tag as ${activeCat.label} (unspecified)`}
          >
            <span
              className="size-1.5 rounded-full shrink-0"
              style={{ backgroundColor: ALL_SECTION_TYPES[activeCat.key]?.hex }}
            />
            All
            {currentType === activeCat.key && <Check className="size-2.5 text-primary" />}
          </button>

          <span className="text-muted-foreground/30 text-[10px]">|</span>

          {activeCat.types.map(type => {
            const meta = ALL_SECTION_TYPES[type]
            const isTagged = currentType === type
            return (
              <button
                key={type}
                className={cn(
                  'flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] transition-colors',
                  isTagged
                    ? 'bg-accent font-medium'
                    : 'hover:bg-accent/50 text-muted-foreground',
                )}
                onClick={() => handleSubTypeClick(type)}
                title={typeLabel(type)}
              >
                <span
                  className="size-1.5 rounded-full shrink-0"
                  style={{ backgroundColor: meta?.hex || '#71717a' }}
                />
                {typeLabel(type)}
                {isTagged && <Check className="size-2.5 text-primary" />}
              </button>
            )
          })}

        </div>
      )}
    </div>
  )
}
