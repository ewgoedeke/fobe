import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from './auth.jsx'
import { ThemeProvider } from './lib/hooks/useTheme.jsx'
import { NavigationProvider } from './lib/hooks/useNavigation.jsx'
import App from './App.jsx'
import 'allotment/dist/style.css'
import './app.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})

class ErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { error: null } }
  static getDerivedStateFromError(error) { return { error } }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 40, color: 'var(--destructive)', background: 'var(--background)', height: '100vh', fontFamily: 'monospace' }}>
          <h2>React crashed</h2>
          <pre style={{ whiteSpace: 'pre-wrap', color: 'var(--destructive)' }}>{this.state.error.message}</pre>
          <pre style={{ whiteSpace: 'pre-wrap', color: 'var(--muted-foreground)', fontSize: 12 }}>{this.state.error.stack}</pre>
          <button onClick={() => { this.setState({ error: null }); window.location.reload() }}
            style={{ marginTop: 16, padding: '8px 16px', background: 'var(--secondary)', color: 'var(--foreground)', border: 'none', borderRadius: 6, cursor: 'pointer' }}>
            Reload
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <QueryClientProvider client={queryClient}>
    <AuthProvider>
      <ThemeProvider>
        <NavigationProvider>
          <ErrorBoundary>
            <App />
          </ErrorBoundary>
        </NavigationProvider>
      </ThemeProvider>
    </AuthProvider>
  </QueryClientProvider>
)
