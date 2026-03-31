import { SidebarProvider, SidebarInset } from '@/components/ui/sidebar.jsx'
import { AppSidebar } from '@/components/AppSidebar.jsx'
import { SiteHeader } from './SiteHeader.jsx'

export default function AppShell({ children }) {
  return (
    <SidebarProvider
      style={{
        '--sidebar-width': 'calc(var(--spacing) * 52)',
        '--header-height': 'calc(var(--spacing) * 12 + 1px)',
      }}
    >
      <AppSidebar variant="inset" />
      <SidebarInset className="border border-sidebar-border overflow-hidden">
        <SiteHeader />
        <div className="flex flex-1 flex-col overflow-hidden">
          <div className="@container/main flex flex-1 flex-col overflow-hidden bg-muted/50">
            {children}
          </div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
