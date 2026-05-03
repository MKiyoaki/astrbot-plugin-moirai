'use client'

import { useState } from 'react'
import { BookOpen } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { useApp } from '@/lib/store'
import { i18n } from '@/lib/i18n'
import * as api from '@/lib/api'

interface LoginScreenProps {
  setupMode: boolean
  onSuccess: () => void
}

export function LoginScreen({ setupMode, onSuccess }: LoginScreenProps) {
  const app = useApp()
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (setupMode) {
      if (password !== confirm) { setError('两次输入不一致'); return }
      if (password.length < 4) { setError('密码至少 4 字符'); return }
    }
    setLoading(true)
    try {
      if (setupMode) {
        await api.auth.setup(password)
      } else {
        await api.auth.login(password)
      }
      await app.refreshAuth()
      await app.refreshStats()
      onSuccess()
    } catch (e: unknown) {
      const err = e as api.ApiError
      setError(err.body || '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-background flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <div className="mb-2 flex justify-center">
            <div className="bg-primary text-primary-foreground flex size-12 items-center justify-center rounded-xl">
              <BookOpen className="size-6" />
            </div>
          </div>
          <CardTitle className="text-xl">
            {setupMode ? i18n.auth.setupTitle : i18n.auth.loginTitle}
          </CardTitle>
          <CardDescription>
            {setupMode ? i18n.auth.setupSubtitle : i18n.auth.subtitle}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="password">
                {setupMode ? i18n.auth.newPassword : i18n.auth.password}
              </Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder={setupMode ? i18n.auth.newPassword : i18n.auth.password}
                autoComplete={setupMode ? 'new-password' : 'current-password'}
                autoFocus
              />
            </div>
            {setupMode && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="confirm">{i18n.auth.confirmPassword}</Label>
                <Input
                  id="confirm"
                  type="password"
                  value={confirm}
                  onChange={e => setConfirm(e.target.value)}
                  placeholder={i18n.auth.confirmPassword}
                  autoComplete="new-password"
                />
              </div>
            )}
            {error && <p className="text-destructive text-sm">{error}</p>}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? '处理中…' : (setupMode ? i18n.auth.setup : i18n.auth.login)}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
