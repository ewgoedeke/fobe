import React, { useState } from 'react'
import { useAuth } from '../auth.jsx'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from './ui/card.jsx'
import { Tabs, TabsList, TabsTrigger, TabsContent } from './ui/tabs.jsx'
import { Input } from './ui/input.jsx'
import { Button } from './ui/button.jsx'
import { Layers } from 'lucide-react'

export default function LoginPage() {
  const { login, signup } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [info, setInfo] = useState(null)
  const [busy, setBusy] = useState(false)

  const handleSubmit = async (e, mode) => {
    e.preventDefault()
    setError(null)
    setInfo(null)
    setBusy(true)
    try {
      if (mode === 'signup') {
        const data = await signup(email, password)
        if (!data.session) {
          setInfo('Check your email for a confirmation link.')
        }
      } else {
        await login(email, password)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const formFields = (
    <div className="flex flex-col gap-3">
      <Input
        type="email"
        placeholder="Email"
        value={email}
        onChange={e => setEmail(e.target.value)}
        required
      />
      <Input
        type="password"
        placeholder="Password"
        value={password}
        onChange={e => setPassword(e.target.value)}
        required
        minLength={6}
      />
      {error && <p className="text-sm text-destructive">{error}</p>}
      {info && <p className="text-sm text-green-600 dark:text-green-400">{info}</p>}
    </div>
  )

  return (
    <div className="flex items-center justify-center h-screen bg-background">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <div className="flex items-center justify-center gap-2 mb-2">
            <div className="flex items-center justify-center size-8 rounded-md bg-primary text-primary-foreground">
              <Layers className="size-4" />
            </div>
          </div>
          <CardTitle className="text-xl">FOBE Explorer</CardTitle>
          <CardDescription>Sign in to access the platform</CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="login">
            <TabsList className="w-full mb-4">
              <TabsTrigger value="login" className="flex-1">Log in</TabsTrigger>
              <TabsTrigger value="signup" className="flex-1">Sign up</TabsTrigger>
            </TabsList>
            <TabsContent value="login">
              <form onSubmit={e => handleSubmit(e, 'login')} className="flex flex-col gap-4">
                {formFields}
                <Button type="submit" disabled={busy} className="w-full">
                  {busy ? 'Signing in...' : 'Log in'}
                </Button>
              </form>
            </TabsContent>
            <TabsContent value="signup">
              <form onSubmit={e => handleSubmit(e, 'signup')} className="flex flex-col gap-4">
                {formFields}
                <Button type="submit" disabled={busy} className="w-full">
                  {busy ? 'Creating account...' : 'Create account'}
                </Button>
              </form>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  )
}
