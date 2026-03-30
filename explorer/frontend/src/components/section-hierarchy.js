/**
 * section-hierarchy.js -- Single source of truth for document section hierarchy (JS).
 *
 * Python mirror: eval/section_types.py
 * Keep these two files in sync.
 */

// ── Floating types ────────────────────────────────────────────────────────
export const FLOATING_TYPES = new Set(['FRONT_MATTER', 'TOC'])

// ── Section groups ────────────────────────────────────────────────────────
export const SECTION_GROUPS = {
  GENERAL_REPORTING: {
    label: 'General Reporting',
    types: [
      'MANAGEMENT_REPORT', 'ESG', 'CORPORATE_GOVERNANCE',
      'RISK_REPORT', 'REMUNERATION_REPORT', 'SUPERVISORY_BOARD',
      'AUDITOR_REPORT', 'RESPONSIBILITY_STATEMENT', 'OTHER',
    ],
  },
  PRIMARY_FINANCIALS: {
    label: 'Primary Financial Statements',
    types: ['PNL', 'SFP', 'OCI', 'CFS', 'SOCIE'],
  },
  NOTES: {
    label: 'Notes to the Financial Statements',
    types: [],
  },
  APPENDIX: {
    label: 'Appendix',
    types: [],
  },
}

// Reverse lookup: content type -> group key
export const TYPE_TO_GROUP = {}
for (const [groupKey, groupDef] of Object.entries(SECTION_GROUPS)) {
  for (const t of groupDef.types) {
    TYPE_TO_GROUP[t] = groupKey
  }
}
TYPE_TO_GROUP['NOTES'] = 'NOTES'
TYPE_TO_GROUP['APPENDIX'] = 'APPENDIX'

// ── Primary statements ────────────────────────────────────────────────────
export const PRIMARY_STATEMENTS = new Set(['PNL', 'SFP', 'OCI', 'CFS', 'SOCIE'])

// ── Rank classes (page classifier) ────────────────────────────────────────
export const RANK_CLASSES = ['TOC', 'PNL', 'SFP', 'OCI', 'CFS', 'SOCIE', 'NOTES', 'OTHER']

// Map from full section type to rank class
export const TYPE_TO_RANK_CLASS = {
  TOC: 'TOC', PNL: 'PNL', SFP: 'SFP', OCI: 'OCI',
  CFS: 'CFS', SOCIE: 'SOCIE', NOTES: 'NOTES',
  FRONT_MATTER: 'OTHER', MANAGEMENT_REPORT: 'OTHER',
  AUDITOR_REPORT: 'OTHER', SUPERVISORY_BOARD: 'OTHER',
  APPENDIX: 'OTHER', OTHER: 'OTHER',
  CORPORATE_GOVERNANCE: 'OTHER', ESG: 'OTHER',
  RISK_REPORT: 'OTHER', REMUNERATION_REPORT: 'OTHER',
  RESPONSIBILITY_STATEMENT: 'OTHER',
}

// ── All section types with metadata ───────────────────────────────────────
export const ALL_SECTION_TYPES = {
  // Floating
  FRONT_MATTER:            { label: 'Front Matter',              bg: 'bg-slate-500/15',   text: 'text-slate-400',   hex: '#94a3b8' },
  TOC:                     { label: 'TOC',                       bg: 'bg-slate-500/15',   text: 'text-slate-400',   hex: '#94a3b8' },
  // Primary financials
  PNL:                     { label: 'Income Statement (PNL)',    bg: 'bg-red-500/15',     text: 'text-red-400',     hex: '#f87171' },
  SFP:                     { label: 'Balance Sheet (SFP)',       bg: 'bg-orange-500/15',  text: 'text-orange-400',  hex: '#fb923c' },
  OCI:                     { label: 'Other Comprehensive Income',bg: 'bg-yellow-500/15',  text: 'text-yellow-400',  hex: '#facc15' },
  CFS:                     { label: 'Cash Flow Statement',       bg: 'bg-green-500/15',   text: 'text-green-400',   hex: '#4ade80' },
  SOCIE:                   { label: 'Changes in Equity',         bg: 'bg-teal-500/15',    text: 'text-teal-400',    hex: '#2dd4bf' },
  // General reporting
  MANAGEMENT_REPORT:       { label: 'Management Report',         bg: 'bg-sky-500/15',     text: 'text-sky-400',     hex: '#38bdf8' },
  ESG:                     { label: 'ESG / Sustainability',      bg: 'bg-emerald-500/15', text: 'text-emerald-400', hex: '#34d399' },
  CORPORATE_GOVERNANCE:    { label: 'Corporate Governance',      bg: 'bg-blue-500/15',    text: 'text-blue-400',    hex: '#60a5fa' },
  RISK_REPORT:             { label: 'Risk Report',               bg: 'bg-rose-500/15',    text: 'text-rose-400',    hex: '#fb7185' },
  REMUNERATION_REPORT:     { label: 'Remuneration Report',       bg: 'bg-pink-500/15',    text: 'text-pink-400',    hex: '#f472b6' },
  SUPERVISORY_BOARD:       { label: 'Supervisory Board Report',  bg: 'bg-fuchsia-500/15', text: 'text-fuchsia-400', hex: '#e879f9' },
  AUDITOR_REPORT:          { label: 'Auditor Report',            bg: 'bg-violet-500/15',  text: 'text-violet-400',  hex: '#a78bfa' },
  RESPONSIBILITY_STATEMENT:{ label: 'Responsibility Statement',  bg: 'bg-indigo-500/15',  text: 'text-indigo-400',  hex: '#818cf8' },
  // Notes & appendix
  NOTES:                   { label: 'Notes',                     bg: 'bg-purple-500/15',  text: 'text-purple-400',  hex: '#c084fc' },
  APPENDIX:                { label: 'Appendix',                  bg: 'bg-cyan-500/15',    text: 'text-cyan-400',    hex: '#22d3ee' },
  // Catch-all
  OTHER:                   { label: 'Other',                     bg: 'bg-zinc-500/15',    text: 'text-zinc-500',    hex: '#71717a' },
}

// Ordered list for UI display
export const TYPE_ORDER = [
  'PNL', 'SFP', 'OCI', 'CFS', 'SOCIE',
  'FRONT_MATTER', 'TOC', 'NOTES',
  'MANAGEMENT_REPORT', 'ESG', 'CORPORATE_GOVERNANCE',
  'RISK_REPORT', 'REMUNERATION_REPORT', 'SUPERVISORY_BOARD',
  'AUDITOR_REPORT', 'RESPONSIBILITY_STATEMENT',
  'APPENDIX', 'OTHER',
]

// UI group structure for dropdowns/selects
export const TYPE_GROUPS_LIST = [
  { key: 'PRIMARY_FINANCIALS', label: 'Primary Financial Statements', types: ['PNL', 'SFP', 'OCI', 'CFS', 'SOCIE'] },
  { key: 'GENERAL_REPORTING', label: 'General Reporting', types: ['MANAGEMENT_REPORT', 'ESG', 'CORPORATE_GOVERNANCE', 'RISK_REPORT', 'REMUNERATION_REPORT', 'SUPERVISORY_BOARD', 'AUDITOR_REPORT', 'RESPONSIBILITY_STATEMENT', 'OTHER'] },
  { key: 'FLOATING', label: 'Structural', types: ['FRONT_MATTER', 'TOC'] },
  { key: 'NOTES', label: 'Notes & Appendix', types: ['NOTES', 'APPENDIX'] },
]
export const GROUP_KEYS = new Set(['ALL', ...TYPE_GROUPS_LIST.map(g => g.key), 'DISC', 'OTHER'])

// ── Helpers ───────────────────────────────────────────────────────────────

export function typeLabel(sectionType) {
  const info = ALL_SECTION_TYPES[sectionType]
  return info ? info.label : sectionType
}

export function typeColor(sectionType) {
  const info = ALL_SECTION_TYPES[sectionType]
  return info ? info.hex : '#71717a'
}

export function isFloating(sectionType) {
  return FLOATING_TYPES.has(sectionType)
}

export function groupForType(sectionType) {
  return TYPE_TO_GROUP[sectionType] || null
}

/**
 * Resolve floating context: determine the group a floating type belongs to
 * based on the nearest following content-type transition.
 *
 * @param {number} page - Page of the floating marker
 * @param {Array<{page: number, section_type: string}>} transitions - Sorted by page
 * @returns {string|null} Group key or null if unresolved
 */
export function resolveFloatingContext(page, transitions) {
  // Find the nearest following non-floating transition
  for (const t of transitions) {
    if (t.page > page && !FLOATING_TYPES.has(t.section_type)) {
      return TYPE_TO_GROUP[t.section_type] || null
    }
  }
  // If no following transition, check preceding
  for (let i = transitions.length - 1; i >= 0; i--) {
    const t = transitions[i]
    if (t.page < page && !FLOATING_TYPES.has(t.section_type)) {
      return TYPE_TO_GROUP[t.section_type] || null
    }
  }
  return null
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
