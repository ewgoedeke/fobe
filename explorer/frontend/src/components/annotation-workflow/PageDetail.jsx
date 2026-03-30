import { useState } from 'react'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card.jsx'
import { Button } from '../ui/button.jsx'
import { Input } from '../ui/input.jsx'
import { Badge } from '../ui/badge.jsx'
import {
  Select, SelectContent, SelectGroup, SelectItem, SelectLabel,
  SelectTrigger, SelectValue,
} from '../ui/select.jsx'
import { Separator } from '../ui/separator.jsx'
import PageWithOverlays from '../PageWithOverlays.jsx'
import { useDocOverlayTables } from '../../api.js'
import {
  ALL_SECTION_TYPES,
  TYPE_GROUPS_LIST,
  typeLabel,
} from '../section-hierarchy.js'
import { Trash2, ArrowLeftRight, X } from 'lucide-react'

/**
 * Full-size page detail panel: page render + features card + action bar.
 */
export function PageDetail({
  docId,
  pageNo,
  pageDims,
  pageMap,
  pageFeatures,
  transition,
  onAddTransition,
  onRemoveTransition,
  onUpdateTransition,
  totalPages,
  multiTags = [],
  onToggleMultiTag,
  onCompareClick,
  hasEdges = false,
}) {
  const { data: allTables = [] } = useDocOverlayTables(docId)
  const tablesOnPage = allTables.filter(t => t.pageNo === pageNo)
  const dims = pageDims?.[pageNo] || pageDims?.[String(pageNo)] || { width: 595, height: 842 }
  const info = pageMap.get(pageNo)
  const features = pageFeatures?.pages?.[pageNo] || pageFeatures?.pages?.[String(pageNo)]
  const pageMultiTags = multiTags.filter(mt => mt.page === pageNo)

  const [selectedType, setSelectedType] = useState(transition?.section_type || info?.type || '')
  const [noteNumber, setNoteNumber] = useState(transition?.note_number || '')

  const handleMark = () => {
    if (!selectedType) return
    onAddTransition({
      page: pageNo,
      section_type: selectedType,
      label: '',
      note_number: noteNumber || null,
      source: 'manual',
      validated: true,
    })
  }

  const handleRemove = () => {
    onRemoveTransition(pageNo)
    setSelectedType('')
    setNoteNumber('')
  }

  return (
    <div className="h-full flex flex-col overflow-y-auto">
      {/* Page render */}
      <div className="p-2 flex-1 min-h-0">
        <PageWithOverlays
          docId={docId}
          pageNo={pageNo}
          pageDims={dims}
          tables={tablesOnPage}
          showDoclingElements={false}
        />
      </div>

      {/* Features card */}
      {features && (
        <Card className="mx-2 mb-2 shrink-0">
          <CardHeader className="py-2 px-3">
            <CardTitle className="text-xs">Page {pageNo} Features</CardTitle>
          </CardHeader>
          <CardContent className="px-3 pb-2 space-y-1.5">
            <FeatureList features={features} />
          </CardContent>
        </Card>
      )}

      {/* Multi-tag section */}
      {(pageMultiTags.length > 0 || info) && (
        <div className="mx-2 mb-2 shrink-0">
          <div className="text-[10px] font-medium text-muted-foreground mb-1">Also tagged as</div>
          <div className="flex flex-wrap gap-1">
            {pageMultiTags.map((mt) => {
              const meta = ALL_SECTION_TYPES[mt.section_type]
              return (
                <Badge
                  key={mt.section_type}
                  variant="secondary"
                  className={cn('text-[10px] px-1.5 py-0 gap-1 cursor-pointer', meta?.bg, meta?.text)}
                  onClick={() => onToggleMultiTag?.(pageNo, mt.section_type)}
                >
                  {typeLabel(mt.section_type)}
                  <X className="size-2.5" />
                </Badge>
              )
            })}
            {/* Add multi-tag via secondary select */}
            <Select
              value=""
              onValueChange={(val) => {
                if (val) onToggleMultiTag?.(pageNo, val)
              }}
            >
              <SelectTrigger className="h-5 w-20 text-[10px] border-dashed">
                <SelectValue placeholder="+ Add" />
              </SelectTrigger>
              <SelectContent>
                {TYPE_GROUPS_LIST.map(group => (
                  <SelectGroup key={group.key}>
                    <SelectLabel className="text-[10px]">{group.label}</SelectLabel>
                    {group.types
                      .filter(t => t !== info?.type && !pageMultiTags.some(mt => mt.section_type === t))
                      .map(t => (
                        <SelectItem key={t} value={t} className="text-xs">
                          <span className="flex items-center gap-1.5">
                            <span
                              className="size-2 rounded-full shrink-0"
                              style={{ backgroundColor: ALL_SECTION_TYPES[t]?.hex }}
                            />
                            {typeLabel(t)}
                          </span>
                        </SelectItem>
                      ))}
                  </SelectGroup>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      )}

      {/* Action bar */}
      <div className="border-t border-border px-3 py-2 shrink-0 space-y-2">
        <div className="flex items-center gap-2">
          <Select value={selectedType} onValueChange={setSelectedType}>
            <SelectTrigger className="h-7 flex-1 text-xs">
              <SelectValue placeholder="Section type..." />
            </SelectTrigger>
            <SelectContent>
              {TYPE_GROUPS_LIST.map(group => (
                <SelectGroup key={group.key}>
                  <SelectLabel className="text-[10px]">{group.label}</SelectLabel>
                  {group.types.map(t => (
                    <SelectItem key={t} value={t} className="text-xs">
                      <span className="flex items-center gap-1.5">
                        <span
                          className="size-2 rounded-full shrink-0"
                          style={{ backgroundColor: ALL_SECTION_TYPES[t]?.hex }}
                        />
                        {typeLabel(t)}
                      </span>
                    </SelectItem>
                  ))}
                </SelectGroup>
              ))}
            </SelectContent>
          </Select>
          <Input
            className="h-7 w-16 text-xs tabular-nums"
            placeholder="Note #"
            value={noteNumber}
            onChange={e => setNoteNumber(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            className="flex-1 h-7 text-xs"
            onClick={handleMark}
            disabled={!selectedType}
          >
            Mark Transition
          </Button>
          {hasEdges && (
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs gap-1"
              onClick={onCompareClick}
            >
              <ArrowLeftRight className="size-3" />
              Compare
            </Button>
          )}
          {transition && (
            <Button
              variant="destructive"
              size="sm"
              className="h-7 text-xs"
              onClick={handleRemove}
            >
              <Trash2 className="size-3" />
            </Button>
          )}
        </div>
        <div className="text-[10px] text-muted-foreground tabular-nums">
          Page {pageNo} of {totalPages}
          {info && (
            <span>
              {' · '}
              <span style={{ color: ALL_SECTION_TYPES[info.type]?.hex }}>
                {info.type}
              </span>
              {info.noteNumber && ` n.${info.noteNumber}`}
              {' · '}
              {info.source}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

function FeatureList({ features }) {
  const predictions = features.predictions || []
  const tocRefs = features.toc_refs || []
  const noteRefs = features.note_refs || []

  return (
    <>
      {predictions.length > 0 && (
        <div>
          <div className="text-[10px] font-medium text-muted-foreground mb-0.5">ML Predictions</div>
          <div className="flex flex-wrap gap-1">
            {predictions.slice(0, 3).map((p, i) => (
              <span
                key={i}
                className={cn(
                  'text-[10px] px-1.5 py-0.5 rounded',
                  ALL_SECTION_TYPES[p.class]?.bg || 'bg-zinc-500/15',
                  ALL_SECTION_TYPES[p.class]?.text || 'text-zinc-500',
                )}
              >
                {p.class} {(p.score * 100).toFixed(0)}%
              </span>
            ))}
          </div>
        </div>
      )}
      {tocRefs.length > 0 && (
        <div>
          <div className="text-[10px] font-medium text-muted-foreground mb-0.5">TOC References</div>
          {tocRefs.map((ref, i) => (
            <div key={i} className="text-[10px] text-sky-400 truncate">
              {ref.label} → p.{ref.page}
            </div>
          ))}
        </div>
      )}
      {noteRefs.length > 0 && (
        <div>
          <div className="text-[10px] font-medium text-muted-foreground mb-0.5">Note References</div>
          {noteRefs.map((ref, i) => (
            <div key={i} className="text-[10px] text-purple-400 truncate">
              {ref.label || `ref ${i + 1}`}
            </div>
          ))}
        </div>
      )}
      {predictions.length === 0 && tocRefs.length === 0 && noteRefs.length === 0 && (
        <div className="text-[10px] text-muted-foreground">No features detected</div>
      )}
    </>
  )
}
