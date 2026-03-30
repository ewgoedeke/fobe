import {
  LayoutDashboard, FileText, Layers, Network, GitBranch,
  ShieldCheck, ClipboardCheck, BookOpen, History, FlaskConical,
  Sun, Moon, LogOut, ChevronUp, Settings
} from 'lucide-react'
import { useNavigation } from '@/lib/hooks/useNavigation.jsx'
import { useTheme } from '@/lib/hooks/useTheme.jsx'
import { useAuth } from '@/auth.jsx'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar.jsx'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu.jsx'
import { Avatar, AvatarFallback } from '@/components/ui/avatar.jsx'

const navPlatform = [
  { id: 'dashboard', title: 'Dashboard', icon: LayoutDashboard },
  { id: 'documents', title: 'Documents', icon: FileText },
  { id: 'elements', title: 'Element Browser', icon: Layers },
  { id: 'ontology', title: 'Ontology', icon: Network },
  { id: 'edges', title: 'Document Edges', icon: GitBranch },
]

const navPipeline = [
  { id: 'training', title: 'Training', icon: FlaskConical },
]

const navQuality = [
  { id: 'ground-truth', title: 'Ground Truth', icon: ShieldCheck },
  { id: 'review', title: 'Review', icon: ClipboardCheck },
  { id: 'annotate', title: 'Annotate', icon: BookOpen },
  { id: 'tag-log', title: 'Tag Log', icon: History },
]

export function AppSidebar(props) {
  const { view, navigate } = useNavigation()
  const { theme, toggleTheme } = useTheme()
  const { user, logout } = useAuth()

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" className="data-[slot=sidebar-menu-button]:!p-1.5" onClick={() => navigate('dashboard')}>
              <div className="flex items-center justify-center size-6 rounded-md bg-sidebar-primary text-sidebar-primary-foreground">
                <Layers className="size-3.5" />
              </div>
              <span className="text-base font-semibold">FOBE</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Platform</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navPlatform.map(item => (
                <SidebarMenuItem key={item.id}>
                  <SidebarMenuButton
                    tooltip={item.title}
                    isActive={view === item.id}
                    disabled={item.disabled}
                    onClick={() => !item.disabled && navigate(item.id)}
                  >
                    <item.icon />
                    <span>{item.title}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupLabel>Pipeline</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navPipeline.map(item => (
                <SidebarMenuItem key={item.id}>
                  <SidebarMenuButton
                    tooltip={item.title}
                    isActive={view === item.id}
                    disabled={item.disabled}
                    onClick={() => !item.disabled && navigate(item.id)}
                  >
                    <item.icon />
                    <span>{item.title}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupLabel>Quality</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navQuality.map(item => (
                <SidebarMenuItem key={item.id}>
                  <SidebarMenuButton
                    tooltip={item.title}
                    isActive={view === item.id}
                    disabled={item.disabled}
                    onClick={() => !item.disabled && navigate(item.id)}
                  >
                    <item.icon />
                    <span>{item.title}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton
                  size="lg"
                  className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
                >
                  <Avatar className="h-8 w-8 rounded-lg">
                    <AvatarFallback className="rounded-lg text-xs">
                      {(user?.email?.split('@')[0]?.slice(0, 2) || 'U').toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
                  <div className="grid flex-1 text-left text-sm leading-tight">
                    <span className="truncate font-medium">{user?.email?.split('@')[0]}</span>
                    <span className="truncate text-xs text-muted-foreground">{user?.email}</span>
                  </div>
                  <ChevronUp className="ml-auto size-4" />
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                className="w-(--radix-dropdown-menu-trigger-width) min-w-56 rounded-lg"
                side="right"
                align="end"
                sideOffset={4}
              >
                <DropdownMenuItem onClick={toggleTheme}>
                  {theme === 'dark' ? <Sun /> : <Moon />}
                  {theme === 'dark' ? 'Light mode' : 'Dark mode'}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={logout}>
                  <LogOut />
                  Log out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  )
}
