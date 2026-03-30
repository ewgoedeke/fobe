import { useDocuments, useStats, useElementsBrowse } from '../api.js'
import { GaapBadge } from './ui/badge.jsx'
import {
  Card, CardHeader, CardTitle, CardDescription, CardFooter
} from './ui/card.jsx'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell
} from './ui/table.jsx'
import { FileText } from 'lucide-react'
import { PdfIndicator } from './ui/pdf-indicator.jsx'
import { useNavigation } from '@/lib/hooks/useNavigation.jsx'

function SectionCards({ documents, browseData, stats }) {
  const docs = browseData?.documents || []

  const totalTables = docs.reduce((sum, d) => {
    const tableCount = Object.values(d.elements || {}).reduce((s, el) => s + (el.tables?.length || 0), 0)
    return sum + tableCount
  }, 0)

  const reviewedDocs = docs.filter(d => d.review?.done).length

  const gaapCounts = {}
  documents.forEach(d => {
    gaapCounts[d.gaap] = (gaapCounts[d.gaap] || 0) + 1
  })

  return (
    <div className="grid grid-cols-1 gap-4 px-4 *:data-[slot=card]:bg-gradient-to-t *:data-[slot=card]:from-primary/5 *:data-[slot=card]:to-card *:data-[slot=card]:shadow-xs *:data-[slot=card]:border lg:px-6 @xl/main:grid-cols-2 @5xl/main:grid-cols-4">
      <Card>
        <CardHeader>
          <CardDescription>Total Documents</CardDescription>
          <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
            {documents.length}
          </CardTitle>
        </CardHeader>
        <CardFooter className="text-sm text-muted-foreground">
          {Object.entries(gaapCounts).map(([g, n]) => `${n} ${g}`).join(' / ')}
        </CardFooter>
      </Card>
      <Card>
        <CardHeader>
          <CardDescription>Total Tables</CardDescription>
          <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
            {totalTables || '...'}
          </CardTitle>
        </CardHeader>
        <CardFooter className="text-sm text-muted-foreground">
          across {documents.length} documents
        </CardFooter>
      </Card>
      <Card>
        <CardHeader>
          <CardDescription>Concepts</CardDescription>
          <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
            {stats?.concepts ?? '...'}
          </CardTitle>
        </CardHeader>
        <CardFooter className="text-sm text-muted-foreground">
          {stats ? `${stats.edges} edges` : null}
        </CardFooter>
      </Card>
      <Card>
        <CardHeader>
          <CardDescription>Reviewed</CardDescription>
          <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
            {reviewedDocs}
          </CardTitle>
        </CardHeader>
        <CardFooter className="text-sm text-muted-foreground">
          of {docs.length} documents
        </CardFooter>
      </Card>
    </div>
  )
}

export default function Dashboard() {
  const { navigate } = useNavigation()
  const { data: stats } = useStats()
  const { data: documents = [] } = useDocuments()
  const { data: browseData } = useElementsBrowse()

  const recentDocs = documents.slice(0, 8)

  return (
    <div className="flex flex-col gap-6 py-6 md:gap-8 md:py-8 overflow-y-auto">
      <div className="px-4 lg:px-6">
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <p className="text-sm text-muted-foreground">Overview of your document corpus and tagging progress</p>
      </div>
      <SectionCards documents={documents} browseData={browseData} stats={stats} />

      {/* Recent documents */}
      <div className="px-4 lg:px-6">
        <h2 className="text-base font-medium text-foreground mb-3">Recent Documents</h2>
        <div className="overflow-hidden rounded-lg border">
          <Table>
            <TableHeader className="bg-muted sticky top-0 z-10">
              <TableRow>
                <TableHead>Document</TableHead>
                <TableHead>GAAP</TableHead>
                <TableHead className="text-right">Pages</TableHead>
                <TableHead className="text-right">Tables</TableHead>
                <TableHead className="text-center">PDF</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {recentDocs.map((doc) => (
                <TableRow
                  key={doc.id}
                  className="cursor-pointer"
                  onClick={() => navigate('elements', { docId: doc.id })}
                >
                  <TableCell>
                    <div className="font-medium">{doc.id}</div>
                    {doc.entity_name && doc.entity_name !== doc.id && (
                      <div className="text-[11px] text-muted-foreground truncate mt-0.5">{doc.entity_name}</div>
                    )}
                  </TableCell>
                  <TableCell><GaapBadge gaap={doc.gaap} /></TableCell>
                  <TableCell className="text-right text-muted-foreground tabular-nums">{doc.page_count || '-'}</TableCell>
                  <TableCell className="text-right text-muted-foreground tabular-nums">{doc.table_count || '-'}</TableCell>
                  <TableCell className="text-center">
                    <PdfIndicator hasPdf={doc.has_pdf} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {documents.length > 8 && (
            <div className="px-4 py-2.5 text-xs text-muted-foreground border-t">
              Showing 8 of {documents.length} documents.{' '}
              <button
                onClick={() => navigate('documents')}
                className="text-primary hover:text-primary/80 cursor-pointer"
              >
                View all
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
