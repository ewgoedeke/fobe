export const TYPE_LABELS = {
  TOC: 'TOC',
  PNL: 'Income Statement (PNL)',
  SFP: 'Balance Sheet (SFP)',
  OCI: 'Other Comprehensive Income',
  CFS: 'Cash Flow Statement',
  SOCIE: 'Changes in Equity',
  NOTES: 'Notes',
  MANAGEMENT_REPORT: 'Management Report',
  AUDITOR_REPORT: 'Auditor Report',
  FRONT_MATTER: 'Front Matter',
  ESG: 'ESG / Sustainability',
  RISK_REPORT: 'Risk Report',
  CORPORATE_GOVERNANCE: 'Corporate Governance',
  UNCLASSIFIED: 'Unclassified',
}

export const TYPE_ORDER = [
  'PNL', 'SFP', 'OCI', 'CFS', 'SOCIE', 'TOC', 'NOTES',
  'MANAGEMENT_REPORT', 'AUDITOR_REPORT', 'FRONT_MATTER', 'ESG',
  'RISK_REPORT', 'CORPORATE_GOVERNANCE',
]

export const RANK_CLASSES = ['TOC', 'PNL', 'SFP', 'OCI', 'CFS', 'SOCIE', 'NOTES', 'OTHER']

export const TYPE_GROUPS = [
  { key: 'PRIMARY', label: 'Primary Financial Statements', types: ['PNL', 'SFP', 'OCI', 'CFS', 'SOCIE'] },
  { key: 'GENERAL', label: 'General Reporting', types: ['MANAGEMENT_REPORT', 'AUDITOR_REPORT', 'CORPORATE_GOVERNANCE', 'ESG', 'RISK_REPORT', 'FRONT_MATTER', 'TOC', 'NOTES'] },
]
export const GROUP_KEYS = new Set(['ALL', ...TYPE_GROUPS.map(g => g.key), 'DISC', 'OTHER'])

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

export function sortTypes(types) {
  return [...types].sort((a, b) => {
    const ai = TYPE_ORDER.indexOf(a)
    const bi = TYPE_ORDER.indexOf(b)
    if (ai >= 0 && bi >= 0) return ai - bi
    if (ai >= 0) return -1
    if (bi >= 0) return 1
    return a.localeCompare(b)
  })
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
