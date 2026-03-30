import React, { useState } from 'react'
import { useSearch } from '@/api.js'
import { Input } from '@/components/ui/input.jsx'
import { Badge } from '@/components/ui/badge.jsx'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '@/components/ui/table.jsx'
import { Search } from 'lucide-react'

export default function BrowseByConcept() {
  const [query, setQuery] = useState('')
  const { data: results = [], isLoading } = useSearch(query)

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b">
        <div className="relative max-w-md">
          <Search className="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground" />
          <Input
            placeholder="Search concepts by ID or label..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            className="pl-8"
          />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        {query.length === 0 ? (
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
            Type to search concepts across the ontology
          </div>
        ) : isLoading ? (
          <div className="p-4 text-sm text-muted-foreground">Searching...</div>
        ) : results.length === 0 ? (
          <div className="p-4 text-sm text-muted-foreground">No concepts found for "{query}"</div>
        ) : (
          <Table>
            <TableHeader className="bg-muted sticky top-0">
              <TableRow>
                <TableHead>Concept ID</TableHead>
                <TableHead>Label</TableHead>
                <TableHead>Context</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {results.map(r => (
                <TableRow key={r.id} className="cursor-pointer hover:bg-accent">
                  <TableCell className="font-mono text-xs">{r.id}</TableCell>
                  <TableCell className="text-sm">{r.label}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-[10px]">{r.context}</Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  )
}
