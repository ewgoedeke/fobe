import {
  FLOATING_TYPES,
  TYPE_TO_GROUP,
  resolveFloatingContext,
} from '../section-hierarchy.js'

/**
 * Resolve transitions into a per-page type map.
 *
 * Each transition carries forward until the next transition.
 * Floating types (FRONT_MATTER, TOC) get their group resolved
 * from the nearest following content-type transition.
 *
 * @param {Array<{page: number, section_type: string, note_number?: string, source?: string}>} transitions
 * @param {number} totalPages
 * @returns {Map<number, {type: string, group: string|null, source: string, noteNumber: string|null}>}
 */
export function resolveTransitions(transitions, totalPages) {
  const sorted = [...transitions].sort((a, b) => a.page - b.page)
  const pageMap = new Map()

  for (let i = 0; i < sorted.length; i++) {
    const t = sorted[i]
    const nextPage = i + 1 < sorted.length ? sorted[i + 1].page : totalPages + 1

    const isFloat = FLOATING_TYPES.has(t.section_type)
    const group = isFloat
      ? resolveFloatingContext(t.page, sorted)
      : (TYPE_TO_GROUP[t.section_type] || null)

    for (let p = t.page; p < nextPage; p++) {
      pageMap.set(p, {
        type: t.section_type,
        group,
        source: t.source || 'manual',
        noteNumber: t.note_number || null,
      })
    }
  }

  return pageMap
}

/**
 * Resolve multi-tags into a per-page set, carrying forward within transition spans.
 *
 * A multi-tag on page N carries forward until either:
 * - A primary transition on a later page resets the span
 * - The same multi-tag type appears again (toggle off)
 *
 * @param {Array<{page: number, section_type: string}>} multiTags
 * @param {Array<{page: number, section_type: string}>} transitions
 * @param {number} totalPages
 * @returns {Map<number, string[]>} page → array of multi-tag section_types
 */
export function resolveMultiTags(multiTags, transitions, totalPages) {
  if (!multiTags.length) return new Map()

  // Build transition boundary pages (sorted)
  const transitionPages = new Set(transitions.map(t => t.page))
  const sortedTransitions = [...transitions].sort((a, b) => a.page - b.page)

  // For each multi-tag, find its transition span and fill forward
  const result = new Map()

  // Sort multi-tags by page
  const sorted = [...multiTags].sort((a, b) => a.page - b.page)

  for (const mt of sorted) {
    // Find the end of this transition span
    let spanEnd = totalPages
    for (const t of sortedTransitions) {
      if (t.page > mt.page) {
        spanEnd = t.page - 1
        break
      }
    }

    // Fill forward from mt.page to spanEnd
    for (let p = mt.page; p <= spanEnd; p++) {
      if (!result.has(p)) result.set(p, [])
      const arr = result.get(p)
      if (!arr.includes(mt.section_type)) arr.push(mt.section_type)
    }
  }

  return result
}

/**
 * Build hierarchy groups from resolved page map for outline display.
 *
 * Returns array of groups, each with sections and page ranges.
 * @param {Map<number, {type, group, source, noteNumber}>} pageMap
 * @param {Array<{page, section_type, label, note_number, source}>} transitions
 * @returns {Array<{group: string, label: string, startPage: number, endPage: number, sections: Array}>}
 */
export function buildHierarchyGroups(pageMap, transitions) {
  const sorted = [...transitions].sort((a, b) => a.page - b.page)
  if (sorted.length === 0) return []

  // Build sections from transitions
  const sections = sorted.map((t, i) => {
    const nextPage = i + 1 < sorted.length ? sorted[i + 1].page : null
    const endPage = nextPage ? nextPage - 1 : Math.max(...pageMap.keys())
    const info = pageMap.get(t.page)
    return {
      type: t.section_type,
      group: info?.group || TYPE_TO_GROUP[t.section_type] || null,
      startPage: t.page,
      endPage,
      label: t.label || '',
      noteNumber: t.note_number || null,
      source: t.source || 'manual',
      validated: t.validated || false,
    }
  })

  // Group contiguous sections by group key
  const groups = []
  let currentGroup = null

  for (const sec of sections) {
    const gKey = sec.group || '_ungrouped'
    if (!currentGroup || currentGroup.groupKey !== gKey) {
      currentGroup = {
        groupKey: gKey,
        startPage: sec.startPage,
        endPage: sec.endPage,
        sections: [sec],
      }
      groups.push(currentGroup)
    } else {
      currentGroup.endPage = sec.endPage
      currentGroup.sections.push(sec)
    }
  }

  return groups
}
