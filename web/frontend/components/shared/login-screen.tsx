'use client'

import { useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import * as api from '@/lib/api'

interface LoginScreenProps {
  onSuccess: () => void
}

export function LoginScreen({ onSuccess }: LoginScreenProps) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async () => {
    if (!password) return
    setLoading(true)
    setError('')
    try {
      await api.auth.login(password)
      onSuccess()
    } catch (e: unknown) {
      const err = e as api.ApiError
      setError(err.status === 401 ? '密码错误' : `登录失败 (${err.status})`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <Card className="w-full max-w-sm">
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl font-serif tracking-tight">Moirai</CardTitle>
          <CardDescription>Memory Engine — 请输入访问密码</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="password">密码</Label>
            <Input
              id="password"
              type="password"
              autoFocus
              value={password}
              onChange={e => setPassword(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') submit() }}
              placeholder="..."
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button onClick={submit} disabled={loading || !password} className="w-full">
            {loading ? '登录中…' : '登录'}
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
