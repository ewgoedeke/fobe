import { cn } from '@/lib/utils'
import { RANK_CLASSES, scorePillClasses } from './constants.js'

/**
 * Classification pill bar — row of RANK_CLASSES buttons, sorted by prediction score.
 *
 * Props:
 *   predictions    — array of { class, score } or null
 *   localTag       — { type, removedFrom } or undefined (from localTags[key])
 *   selectedType   — currently browsed element type (e.g., 'PNL')
 *   isPred         — whether this page is a predicted (not GT) page
 *   isSaving       — whether a save is in progress for this page
 *   onTag          — (tagType, removeFrom) => void
 *   compact        — if true, use smaller padding (for gallery thumbnails)
 */
export function ClassificationBar({
  predictions,
  localTag,
  selectedType,
  isPred = false,
  isSaving = false,
  onTag,
  compact = false,
}) {
  const predMap = {}
  if (predictions) predictions.forEach(p => { predMap[p.class] = p.score })
  const allClasses = RANK_CLASSES.map(cls => ({ class: cls, score: predMap[cls] || 0 }))
  allClasses.sort((a, b) => b.score - a.score || RANK_CLASSES.indexOf(a.class) - RANK_CLASSES.indexOf(b.class))
  const topScore = allClasses[0]?.score || 0

  const isLocallyTagged = localTag?.type != null
  const isLocallyRemoved = localTag?.type === null && localTag?.removedFrom

  return (
    <div className={cn(
      'flex gap-1 flex-wrap items-center border-b border-border min-h-[22px]',
      compact ? 'px-1.5 py-0.5' : 'px-3 py-1.5',
      isPred && !isLocallyTagged ? 'bg-violet-950/30' : 'bg-muted/50',
    )}>
      {allClasses.map(p => {
        const isSelected = p.class === selectedType
        const isTaggedType = isLocallyTagged && p.class === localTag.type
        const isRemovedType = isLocallyRemoved && p.class === localTag.removedFrom && isSelected
        const isTopPred = p.score === topScore && p.score > 0

        const handleClick = () => {
          if (isSaving || !onTag) return
          if (localTag) {
            if (isTaggedType) {
              onTag(null, p.class)
            } else if (isRemovedType) {
              onTag(selectedType, null)
            } else if (isPred) {
              onTag(p.class, null)
            } else {
              onTag(p.class, selectedType)
            }
          } else if (isPred) {
            onTag(p.class, null)
          } else if (isSelected) {
            onTag(null, selectedType)
          } else {
            onTag(p.class, selectedType)
          }
        }

        // Determine pill styling
        let pillClass
        if (isTaggedType) {
          pillClass = 'bg-green-500/20 border-green-500/40 text-green-500 font-bold'
        } else if (isRemovedType) {
          pillClass = 'bg-destructive/20 border-destructive/40 text-destructive font-bold'
        } else if (isSelected && !localTag) {
          pillClass = cn(scorePillClasses(p.score), 'font-bold')
        } else if (isTopPred) {
          pillClass = 'border-transparent text-muted-foreground'
        } else {
          pillClass = 'border-transparent text-muted-foreground/50'
        }

        return (
          <button
            key={p.class}
            onClick={handleClick}
            disabled={isSaving}
            className={cn(
              'rounded font-mono whitespace-nowrap border cursor-pointer',
              compact ? 'px-1.5 py-px text-[10px]' : 'px-2.5 py-1 text-xs',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              'hover:bg-accent/50 transition-colors',
              pillClass,
            )}
          >
            {p.class}{p.score > 0 ? ` ${(p.score * 100).toFixed(0)}%` : ''}
          </button>
        )
      })}
    </div>
  )
}
