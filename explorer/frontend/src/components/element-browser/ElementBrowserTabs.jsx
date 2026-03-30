import React from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs.jsx'
import ElementBrowser from './ElementBrowser.jsx'
import BrowseByConcept from './BrowseByConcept.jsx'
import BrowseByAxis from './BrowseByAxis.jsx'
import BrowseByDocument from './BrowseByDocument.jsx'

export default function ElementBrowserTabs() {
  return (
    <Tabs defaultValue="statement" className="flex flex-col h-full overflow-hidden">
      <div className="border-b px-4 lg:px-6 shrink-0">
        <TabsList className="h-9">
          <TabsTrigger value="statement" className="text-xs">Statement Type</TabsTrigger>
          <TabsTrigger value="concept" className="text-xs">Concept</TabsTrigger>
          <TabsTrigger value="axis" className="text-xs">Axis</TabsTrigger>
          <TabsTrigger value="document" className="text-xs">Document</TabsTrigger>
        </TabsList>
      </div>
      <TabsContent value="statement" className="flex-1 flex flex-col overflow-hidden mt-0">
        <ElementBrowser />
      </TabsContent>
      <TabsContent value="concept" className="flex-1 flex flex-col overflow-hidden mt-0">
        <BrowseByConcept />
      </TabsContent>
      <TabsContent value="axis" className="flex-1 flex flex-col overflow-hidden mt-0">
        <BrowseByAxis />
      </TabsContent>
      <TabsContent value="document" className="flex-1 flex flex-col overflow-hidden mt-0">
        <BrowseByDocument />
      </TabsContent>
    </Tabs>
  )
}
