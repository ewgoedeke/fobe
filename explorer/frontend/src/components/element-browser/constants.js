// Re-export hierarchy definitions from SSoT
export {
  ALL_SECTION_TYPES as TYPE_LABELS_MAP,
  RANK_CLASSES,
  TYPE_ORDER,
  TYPE_GROUPS_LIST as TYPE_GROUPS,
  GROUP_KEYS,
  sortTypes,
  typeLabel,
} from '../section-hierarchy.js'

import { ALL_SECTION_TYPES, TYPE_ORDER } from '../section-hierarchy.js'

// Legacy TYPE_LABELS: { KEY: "Label" } for backward compat
export const TYPE_LABELS = Object.fromEntries(
  Object.entries(ALL_SECTION_TYPES).map(([k, v]) => [k, v.label])
)

/** Tailwind text color class based on confidence score */
export function scoreTextClass(score) {
  if (score >= 0.8) return 'text-green-500'
  if (score >= 0.5) return 'text-yellow-500'
  if (score >= 0.3) return 'text-orange-500'
  return 'text-red-500'
}

/** Tailwind bg + border classes for classification pills based on score */
export function scorePillClasses(score) {
  if (score >= 0.8) return 'bg-green-500/15 border-green-500/30 text-green-500'
  if (score >= 0.5) return 'bg-yellow-500/15 border-yellow-500/30 text-yellow-500'
  if (score >= 0.3) return 'bg-orange-500/15 border-orange-500/30 text-orange-500'
  return 'bg-red-500/15 border-red-500/30 text-red-500'
}

export function addPageToSections(sections, pageNo, type) {
  const matching = sections.filter(s => s.statement_type === type)
  for (const s of matching) {
    if (pageNo >= s.start_page - 1 && pageNo <= s.end_page + 1) {
      s.start_page = Math.min(s.start_page, pageNo)
      s.end_page = Math.max(s.end_page, pageNo)
      return sections
    }
  }
  sections.push({
    label: '',
    statement_type: type,
    start_page: pageNo,
    end_page: pageNo,
    note_number: null,
    validated: true,
  })
  return sections
}

export function removePageFromSections(sections, pageNo, type) {
  const result = []
  for (const s of sections) {
    if (s.statement_type !== type) { result.push(s); continue }
    if (pageNo < s.start_page || pageNo > s.end_page) { result.push(s); continue }
    if (s.start_page === s.end_page) continue
    if (pageNo === s.start_page) { s.start_page++; result.push(s) }
    else if (pageNo === s.end_page) { s.end_page--; result.push(s) }
    else {
      result.push({ ...s, end_page: pageNo - 1 })
      result.push({ ...s, start_page: pageNo + 1 })
    }
  }
  return result
}
