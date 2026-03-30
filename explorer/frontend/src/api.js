import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

// ── Fetch helper ─────────────────────────────────────────
// Attaches auth token from localStorage if available.

function _getToken() {
  try {
    const raw = localStorage.getItem('fobe_session')
    return raw ? JSON.parse(raw).access_token : null
  } catch { return null }
}

async function fetchJSON(url, opts = {}) {
  const token = _getToken()
  if (token) {
    opts.headers = { ...opts.headers, Authorization: `Bearer ${token}` }
  }
  const res = await fetch(url, opts)
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body.error) detail = body.error
    } catch {}
    throw new Error(detail)
  }
  return res.json()
}

// ── Ontology queries ─────────────────────────────────────

export function useStats() {
  return useQuery({
    queryKey: ['stats'],
    queryFn: () => fetchJSON('/api/stats'),
    staleTime: 5 * 60_000,
  })
}

export function useDocuments() {
  return useQuery({
    queryKey: ['documents'],
    queryFn: () => fetchJSON('/api/documents').then(d => d.documents || []),
    staleTime: 5 * 60_000,
  })
}


export function useDocumentStats() {
  return useQuery({
    queryKey: ['document-stats'],
    queryFn: () => fetchJSON('/api/documents/stats').then(d => d.stats || []),
    staleTime: 30_000,
  })
}

// ── Ontology tree ───────────────────────────────────────

export function useOntologyContexts() {
  return useQuery({
    queryKey: ['ontology-contexts'],
    queryFn: () => fetchJSON('/api/ontology/contexts').then(d => d.contexts || []),
    staleTime: 5 * 60_000,
  })
}

export function useOntologyContextTree(contextId) {
  return useQuery({
    queryKey: ['ontology-context-tree', contextId],
    queryFn: () => fetchJSON(`/api/ontology/context/${contextId}`),
    enabled: !!contextId,
    staleTime: 5 * 60_000,
  })
}

export function useOntologyConceptDetail(conceptId) {
  return useQuery({
    queryKey: ['ontology-concept-detail', conceptId],
    queryFn: () => fetchJSON(`/api/ontology/concept/${conceptId}`),
    enabled: !!conceptId,
    staleTime: 5 * 60_000,
  })
}

export function useConcept(conceptId) {
  return useQuery({
    queryKey: ['concept', conceptId],
    queryFn: () => fetchJSON(`/api/concept/${conceptId}`),
    enabled: !!conceptId,
    staleTime: 60_000,
  })
}

export function useConceptPages(conceptId) {
  return useQuery({
    queryKey: ['concept-pages', conceptId],
    queryFn: () => fetchJSON(`/api/concept-pages/${conceptId}`).then(d => d.pages || []),
    enabled: !!conceptId,
    staleTime: 60_000,
  })
}

export function useSearch(query) {
  return useQuery({
    queryKey: ['search', query],
    queryFn: () => fetchJSON(`/api/search?q=${encodeURIComponent(query)}`).then(d => d.results || []),
    enabled: query.length >= 1,
    staleTime: 30_000,
  })
}

// ── Table data ───────────────────────────────────────────

export function useTables(docId) {
  return useQuery({
    queryKey: ['tables', docId],
    queryFn: () => fetchJSON(`/api/tables/${docId}`).then(d => d.tables || []),
    enabled: !!docId,
    staleTime: 2 * 60_000,
  })
}

// ── Docling elements ─────────────────────────────────────

export function useDoclingElements(docId, pageNo, enabled = true) {
  return useQuery({
    queryKey: ['docling-elements', docId, pageNo],
    queryFn: () => fetchJSON(`/api/docling-elements/${docId}/${pageNo}`).then(d => d.elements || []),
    enabled: !!docId && !!pageNo && enabled,
    staleTime: 5 * 60_000,
  })
}

// ── Review ───────────────────────────────────────────────

export function useReviewStatus() {
  return useQuery({
    queryKey: ['review-status'],
    queryFn: () => fetchJSON('/api/review/status').then(d => d.fixtures || []),
    staleTime: 30_000,
  })
}

export function useReviewDoc(docId) {
  return useQuery({
    queryKey: ['review-doc', docId],
    queryFn: () => Promise.all([
      fetchJSON(`/api/review/${docId}/tables`),
      fetchJSON(`/api/review/${docId}`),
      fetchJSON(`/api/review/${docId}/human`),
    ]).then(([tablesData, manifestData, humanData]) => ({
      tables: tablesData.tables || [],
      manifest: manifestData.error ? null : manifestData,
      human: humanData,
    })),
    enabled: !!docId,
    staleTime: 30_000,
  })
}

export function useReviewSave(docId) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => fetchJSON(`/api/review/${docId}/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['review-doc', docId] })
      qc.invalidateQueries({ queryKey: ['review-status'] })
    },
  })
}

// ── Annotate (TOC) ───────────────────────────────────────

export function useAnnotateDocuments() {
  return useQuery({
    queryKey: ['annotate-documents'],
    queryFn: () => fetchJSON('/api/annotate/documents').then(d => d.documents || []),
    staleTime: 30_000,
  })
}

export function useAnnotateToc(docId) {
  return useQuery({
    queryKey: ['annotate-toc', docId],
    queryFn: () => fetchJSON(`/api/annotate/${docId}/toc`),
    enabled: !!docId,
    staleTime: 30_000,
  })
}

export function useAnnotateSave(docId) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (groundTruth) => fetchJSON(`/api/annotate/${docId}/toc`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(groundTruth),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['annotate-toc', docId] })
      qc.invalidateQueries({ queryKey: ['annotate-documents'] })
    },
  })
}

export function useAnnotateDetect(docId) {
  return useMutation({
    mutationFn: () => fetchJSON(`/api/annotate/${docId}/toc/detect`),
  })
}

export function useAnnotateValidate(docId) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (groundTruth) =>
      fetchJSON(`/api/annotate/${docId}/toc`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(groundTruth),
      }).then(() => fetchJSON(`/api/annotate/${docId}/validate`, { method: 'POST' })),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['annotate-toc', docId] })
    },
  })
}

// ── Annotation v2 ────────────────────────────────────────

export function usePageFeatures(docId) {
  return useQuery({
    queryKey: ['page-features', docId],
    queryFn: () => fetchJSON(`/api/annotate/${docId}/page-features`),
    enabled: !!docId,
    staleTime: 60_000,
  })
}

export function useTocEntries(docId) {
  return useQuery({
    queryKey: ['toc-entries', docId],
    queryFn: () => fetchJSON(`/api/annotate/${docId}/toc/entries`),
    enabled: !!docId,
    staleTime: 60_000,
  })
}

export function useSaveTransitions(docId) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (transitions) => fetchJSON(`/api/annotate/${docId}/transitions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(transitions),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['annotate-toc', docId] })
      qc.invalidateQueries({ queryKey: ['annotate-documents'] })
    },
  })
}

// ── Elements Browser ─────────────────────────────────────

export function useElementsBrowse() {
  return useQuery({
    queryKey: ['elements-browse'],
    queryFn: () => fetchJSON('/api/elements/browse'),
    staleTime: 30_000,
  })
}

export function useElementsDetail(docId) {
  return useQuery({
    queryKey: ['elements-detail', docId],
    queryFn: () => fetchJSON(`/api/elements/browse/${docId}/detail`),
    enabled: !!docId,
    staleTime: 60_000,
  })
}

export function useDocOverlayTables(docId, enabled = true) {
  return useQuery({
    queryKey: ['doc-overlay-tables', docId],
    queryFn: () => fetchJSON(`/api/elements/browse/${docId}/tables`).then(d => d.tables || []),
    enabled: !!docId && enabled,
    staleTime: 5 * 60_000,
  })
}

export function useElementsRetrain() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => fetchJSON('/api/elements/retrain', { method: 'POST' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['elements-browse'] })
    },
  })
}

export function useElementsReview(docId, elementType) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ method = 'POST', body } = {}) => fetch(`/api/elements/review/${docId}/${elementType}`, {
      method,
      ...(body ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}),
    }).then(r => r.json()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['elements-browse'] })
    },
  })
}

// ── Voting ──────────────────────────────────────────────────

export function useVotes(dimension, targetId) {
  return useQuery({
    queryKey: ['votes', dimension, targetId],
    queryFn: () => fetchJSON(`/api/votes/${dimension}/${targetId}`),
    enabled: !!dimension && !!targetId,
    staleTime: 15_000,
  })
}

export function useVoteConflicts(docId) {
  return useQuery({
    queryKey: ['vote-conflicts', docId],
    queryFn: () => fetchJSON(`/api/votes/conflicts/${docId}`).then(d => d.conflicts || []),
    enabled: !!docId,
    staleTime: 30_000,
  })
}

export function useCastVote() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vote) => fetchJSON('/api/votes/cast', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(vote),
    }),
    onSuccess: (_data, vote) => {
      qc.invalidateQueries({ queryKey: ['votes', vote.dimension, vote.target_id] })
      qc.invalidateQueries({ queryKey: ['vote-conflicts'] })
    },
  })
}

// ── Ground Truth Sets ────────────────────────────────────────

export function useGTSets() {
  return useQuery({
    queryKey: ['gt-sets'],
    queryFn: () => fetchJSON('/api/gt/sets').then(d => d.sets || []),
    staleTime: 30_000,
  })
}

export function useGTSetDocs(setId) {
  return useQuery({
    queryKey: ['gt-set-docs', setId],
    queryFn: () => fetchJSON(`/api/gt/sets/${setId}/docs`).then(d => d.docs || []),
    enabled: !!setId,
    staleTime: 30_000,
  })
}

export function useCreateGTSet() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => fetchJSON('/api/gt/sets', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['gt-sets'] }),
  })
}

export function useAddGTSetDocs(setId) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (docIds) => fetchJSON(`/api/gt/sets/${setId}/docs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ doc_ids: docIds }),
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['gt-set-docs', setId] }),
  })
}

// ── Document Edges ──────────────────────────────────────────

export function useDocEdges(docId) {
  return useQuery({
    queryKey: ['doc-edges', docId],
    queryFn: () => fetchJSON(`/api/edges/${docId}`).then(d => d.edges || []),
    enabled: !!docId,
    staleTime: 30_000,
  })
}

export function useCreateEdge(docId) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (edge) => fetchJSON(`/api/edges/${docId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(edge),
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['doc-edges', docId] }),
  })
}

export function useValidateEdge(docId) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ edgeId, updates }) => fetchJSON(`/api/edges/${edgeId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['doc-edges', docId] }),
  })
}

export function useDeleteEdge(docId) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (edgeId) => fetchJSON(`/api/edges/${edgeId}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['doc-edges', docId] }),
  })
}

export function useAutoDetectEdges(docId) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => fetchJSON(`/api/edges/${docId}/auto-detect`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['doc-edges', docId] }),
  })
}

// ── Tag Log ─────────────────────────────────────────────────

export function useTagLog() {
  return useQuery({
    queryKey: ['tag-log'],
    queryFn: () => fetchJSON('/api/tag-log').then(d => d.entries || []),
    staleTime: 30_000,
  })
}

export function logTagAction(entry) {
  return fetchJSON('/api/tag-log', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(entry),
  }).catch(() => {}) // fire-and-forget
}

// ── Ontology Gaps ──────────────────────────────────────────────

export function useOntologyGaps(status, context) {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  if (context) params.set('context', context)
  const qs = params.toString()
  return useQuery({
    queryKey: ['ontology-gaps', status, context],
    queryFn: () => fetchJSON(`/api/ontology/gaps${qs ? `?${qs}` : ''}`).then(d => d.gaps || []),
    staleTime: 30_000,
  })
}

export function useCreateGap() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => fetchJSON('/api/ontology/gaps', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ontology-gaps'] }),
  })
}

export function useUpdateGap() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ gapId, updates }) => fetchJSON(`/api/ontology/gaps/${gapId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ontology-gaps'] }),
  })
}

// ── Concept Proposals ──────────────────────────────────────────

export function useConceptProposals(status) {
  const qs = status ? `?status=${status}` : ''
  return useQuery({
    queryKey: ['concept-proposals', status],
    queryFn: () => fetchJSON(`/api/ontology/proposals${qs}`).then(d => d.proposals || []),
    staleTime: 30_000,
  })
}

export function useCreateProposal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => fetchJSON('/api/ontology/proposals', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['concept-proposals'] })
      qc.invalidateQueries({ queryKey: ['ontology-gaps'] })
    },
  })
}

export function useUpdateProposal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ proposalId, updates }) => fetchJSON(`/api/ontology/proposals/${proposalId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['concept-proposals'] }),
  })
}

export function useAcceptProposal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (proposalId) => fetchJSON(`/api/ontology/proposals/${proposalId}/accept`, {
      method: 'POST',
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['concept-proposals'] })
      qc.invalidateQueries({ queryKey: ['ontology-gaps'] })
    },
  })
}

export function useRejectProposal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (proposalId) => fetchJSON(`/api/ontology/proposals/${proposalId}/reject`, {
      method: 'POST',
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['concept-proposals'] })
      qc.invalidateQueries({ queryKey: ['ontology-gaps'] })
    },
  })
}

// ── Pipeline Runs ──────────────────────────────────────────────

export function useRunDefaults() {
  return useQuery({
    queryKey: ['run-defaults'],
    queryFn: () => fetchJSON('/api/runs/defaults'),
    staleTime: 5 * 60_000,
  })
}

export function useRuns() {
  return useQuery({
    queryKey: ['runs'],
    queryFn: () => fetchJSON('/api/runs').then(d => d.runs || []),
    staleTime: 10_000,
  })
}

export function useRun(runId) {
  return useQuery({
    queryKey: ['run', runId],
    queryFn: () => fetchJSON(`/api/runs/${runId}`),
    enabled: !!runId,
    staleTime: 3_000,
    refetchInterval: (query) => {
      const data = query.state.data
      return data?.status === 'running' ? 3000 : false
    },
  })
}

export function useRunResults(runId) {
  return useQuery({
    queryKey: ['run-results', runId],
    queryFn: () => fetchJSON(`/api/runs/${runId}/results`).then(d => d.results || []),
    enabled: !!runId,
    staleTime: 5_000,
  })
}

export function useCreateRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => fetchJSON('/api/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['runs'] }),
  })
}

export function useCancelRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (runId) => fetchJSON(`/api/runs/${runId}/cancel`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['runs'] }),
  })
}
