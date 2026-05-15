'use client'

import { useState, useEffect } from 'react'
import { useTheme } from 'next-themes'
import { Eye, EyeOff, Moon, Sun, Languages } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { useApp } from '@/lib/store'
import { getStored, setStored } from '@/lib/safe-storage'
import * as api from '@/lib/api'

const THEMES = [
  { id: 'moirai', label: 'Moirai' },
  { id: 'nox', label: 'Nox' },
  { id: 'venus', label: 'Venus' },
  { id: 'juno', label: 'Cirrus' },
  { id: 'augustus', label: 'Augustus' },
  { id: 'selune', label: 'Aether' },
  { id: 'folio', label: 'Folio' },
]

const THEME_ACCENT_COLORS: Record<string, string> = {
  moirai: 'oklch(0.53 0.130 295)',
  nox: 'oklch(0.45 0.08 260)',
  venus: 'oklch(0.60 0.18 5)',
  juno: 'oklch(0.52 0.12 220)',
  augustus: 'oklch(0.58 0.14 55)',
  selune: 'oklch(0.55 0.10 200)',
  folio: 'oklch(0.48 0.09 140)',
}

const LANG_LABELS: Record<string, string> = { zh: '中', en: 'EN', ja: '日' }

interface LoginScreenProps {
  onSuccess: () => void
}

export function LoginScreen({ onSuccess }: LoginScreenProps) {
  const { lang, setLang, preAuthVersion } = useApp()
  const { resolvedTheme, setTheme } = useTheme()
  const isDark = resolvedTheme === 'dark'

  const [password, setPassword] = useState('')
  const [showPwd, setShowPwd] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const [colorScheme, setColorScheme] = useState(() =>
    getStored('em_color_scheme', 'moirai') || 'moirai'
  )

  // Apply color scheme changes in real time
  useEffect(() => {
    const root = document.documentElement
    THEMES.forEach(t => root.classList.remove(`theme-${t.id}`))
    if (colorScheme !== 'zinc') root.classList.add(`theme-${colorScheme}`)
    setStored('em_color_scheme', colorScheme)
  }, [colorScheme])

  const submit = async () => {
    if (!password) return
    setLoading(true)
    setError('')
    try {
      await api.auth.login(password)
      onSuccess()
    } catch (e: unknown) {
      const err = e as api.ApiError
      if (lang === 'en') setError(err.status === 401 ? 'Incorrect passphrase' : `Login failed (${err.status})`)
      else if (lang === 'ja') setError(err.status === 401 ? 'パスフレーズが違います' : `ログイン失敗 (${err.status})`)
      else setError(err.status === 401 ? '密码错误' : `登录失败 (${err.status})`)
    } finally {
      setLoading(false)
    }
  }

  const t = {
    zh: {
      issue: '档案',
      enterArchive: '+ 进入控制台',
      welcome: '欢迎回来。',
      singleField: '→ 单字段密码登录',
      continueWeave: '输入访问密码以继续。',
      passphrase: '密码 / PASSPHRASE',
      forgot: '忘记？',
      forgotTip: '在 AstrBot 面板查看插件日志中的随机 Token，或在插件配置中手动设置密码。',
      enter: '进入控制台',
      tagline: <>AstrBot AI Agent 的<br /><span style={{ color: 'var(--color-primary, oklch(0.53 0.130 295))' }}>长期记忆</span>与社交关系管理面板。</>,
    },
    en: {
      issue: 'ISSUE',
      enterArchive: '+ ENTER CONSOLE',
      welcome: 'Welcome back.',
      singleField: '→ Single-field passphrase',
      continueWeave: 'Enter your password to continue.',
      passphrase: 'PASSPHRASE',
      forgot: 'Forgot?',
      forgotTip: 'Check the random token in the AstrBot panel plugin logs, or set a password manually in plugin config.',
      enter: 'Enter Console',
      tagline: <>Long-term <span style={{ color: 'var(--color-primary, oklch(0.53 0.130 295))' }}>memory</span> &amp; social relationship<br />management panel for AstrBot AI Agent.</>,
    },
    ja: {
      issue: 'アーカイブ',
      enterArchive: '+ コンソールへ',
      welcome: 'おかえりなさい。',
      singleField: '→ 単一フィールド認証',
      continueWeave: 'パスワードを入力して続けてください。',
      passphrase: 'パスフレーズ / PASSPHRASE',
      forgot: '忘れた？',
      forgotTip: 'AstrBot パネルのプラグインログでランダムトークンを確認するか、プラグイン設定でパスワードを手動設定してください。',
      enter: 'コンソールへ',
      tagline: <>AstrBot AI Agent の<span style={{ color: 'var(--color-primary, oklch(0.53 0.130 295))' }}>長期記憶</span>と<br />ソーシャル関係管理パネル。</>,
    },
  }

  const copy = t[lang]

  return (
    <div className="min-h-screen flex flex-col bg-background text-foreground">
      {/* ── Main content ─────────────────────────────────── */}
      <div className="flex-1 flex flex-col md:flex-row">

        {/* Left panel — editorial cover (desktop only) */}
        <div className="hidden md:flex md:w-2/5 flex-col justify-between p-10 border-r border-border relative overflow-hidden select-none">
          {/* Silk thread background */}
          <svg className="absolute inset-0 w-full h-full pointer-events-none" aria-hidden preserveAspectRatio="none" viewBox="0 0 400 700">
            <defs>
              <style>{`
                @keyframes silk-flow {
                  0%   { stroke-dashoffset: 0; }
                  100% { stroke-dashoffset: -600; }
                }
                @keyframes silk-shimmer {
                  0%, 100% { opacity: 0.55; }
                  50%       { opacity: 0.85; }
                }
                .thread-accent {
                  stroke-dasharray: 320 120;
                  animation: silk-flow 7s linear infinite, silk-shimmer 4s ease-in-out infinite;
                }
              `}</style>
            </defs>

            {/* Background threads — muted, subtly curved */}
            <path d="M-10,148 Q80,142 180,155 Q280,168 410,151" fill="none" stroke="currentColor" strokeWidth="0.4" opacity="0.18" />
            <path d="M-10,220 Q60,228 160,215 Q260,202 410,224" fill="none" stroke="currentColor" strokeWidth="0.3" opacity="0.14" />
            <path d="M-10,310 Q100,298 200,318 Q300,328 410,308" fill="none" stroke="currentColor" strokeWidth="0.45" opacity="0.16" />
            <path d="M-10,420 Q90,432 190,418 Q290,405 410,428" fill="none" stroke="currentColor" strokeWidth="0.3" opacity="0.12" />
            <path d="M-10,510 Q120,502 210,516 Q310,525 410,506" fill="none" stroke="currentColor" strokeWidth="0.4" opacity="0.15" />
            <path d="M-10,580 Q70,575 170,588 Q270,598 410,574" fill="none" stroke="currentColor" strokeWidth="0.3" opacity="0.10" />

            {/* Accent silk thread — animated flow */}
            <path
              className="thread-accent"
              d="M-10,265 Q60,252 140,270 Q220,288 310,260 Q360,247 410,268"
              fill="none"
              stroke="var(--color-primary, oklch(0.53 0.130 295))"
              strokeWidth="0.7"
              strokeLinecap="round"
            />

            {/* Knot-like nodes where threads cross */}
            <circle cx="112" cy="155" r="1.8" fill="currentColor" opacity="0.20" />
            <circle cx="248" cy="310" r="1.4" fill="currentColor" opacity="0.16" />
            <circle cx="310" cy="261" r="2" fill="var(--color-primary, oklch(0.53 0.130 295))" opacity="0.30" />
            <circle cx="168" cy="510" r="1.3" fill="currentColor" opacity="0.14" />
          </svg>

          {/* Cover top label */}
          <div className="relative z-10">
            <div className="flex items-center gap-3 font-mono text-[9px] uppercase tracking-[0.22em] text-muted-foreground/60 mb-1">
              <span>MOIΡΑΙ</span>
              <span>·</span>
              <span>{copy.issue} {preAuthVersion}</span>
              <span>·</span>
              <span className="flex items-center gap-1">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                ENGINE LIVE
              </span>
            </div>
          </div>

          {/* Cover logo + tagline */}
          <div className="relative z-10">
            <h1 className="font-serif text-6xl font-bold tracking-tight leading-none mb-6">
              <span className="text-foreground">Moí</span>
              <span style={{ color: 'var(--color-primary, oklch(0.53 0.130 295))' }}>π</span>
              <span className="text-foreground">αι</span>
              <span style={{ color: 'var(--color-primary, oklch(0.53 0.130 295))' }}>.</span>
            </h1>
            <p className="text-lg leading-snug text-muted-foreground">
              {copy.tagline}
            </p>
          </div>

          {/* Cover bottom */}
          <div className="relative z-10 font-mono text-[9px] uppercase tracking-[0.18em] text-muted-foreground/40">
            EST · MMXXVI — V {preAuthVersion}
          </div>
        </div>

        {/* Right panel — login form */}
        <div className="flex-1 flex flex-col justify-between p-8 md:p-12 max-w-lg mx-auto w-full">
          {/* Form top label */}
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground/50 mb-8">
            {copy.enterArchive}
          </div>

          {/* Form body */}
          <div className="flex-1 flex flex-col justify-center gap-6">
            <div>
              <h2 className="font-serif text-4xl font-bold tracking-tight text-foreground mb-1">
                {copy.welcome}
              </h2>
              <p className="font-mono text-[10px] text-muted-foreground/50 tracking-widest mb-4">
                {copy.singleField}
              </p>
              <p className="text-sm text-muted-foreground">
                {copy.continueWeave}
              </p>
            </div>

            {/* Passphrase field */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground/60">
                  {copy.passphrase}
                </label>
                <div className="relative group">
                  <button
                    type="button"
                    className="font-mono text-[10px] uppercase tracking-widest text-primary underline underline-offset-2 hover:opacity-70"
                    tabIndex={-1}
                  >
                    {copy.forgot}
                  </button>
                  <div className="absolute right-0 bottom-full mb-2 w-64 rounded border border-border bg-popover px-3 py-2 text-[11px] text-popover-foreground shadow-md opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-50 normal-case tracking-normal font-sans">
                    {copy.forgotTip}
                  </div>
                </div>
              </div>
              <div className="relative flex items-center border-b border-foreground/30 focus-within:border-primary transition-colors">
                <Input
                  type={showPwd ? 'text' : 'password'}
                  autoFocus
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') submit() }}
                  className="border-0 border-none shadow-none rounded-none bg-transparent px-0 py-2 text-base focus-visible:ring-0 focus-visible:outline-none"
                  placeholder="• • • • • • • • • • •"
                />
                <button
                  type="button"
                  onClick={() => setShowPwd(v => !v)}
                  className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground hover:text-foreground ml-2 shrink-0"
                >
                  {showPwd ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
                </button>
              </div>
              {error && (
                <p className="text-xs text-destructive font-mono tracking-wide">{error}</p>
              )}
            </div>

            {/* Submit */}
            <Button
              onClick={submit}
              disabled={loading || !password}
              className="w-full rounded-none h-12 font-mono text-sm uppercase tracking-[0.15em]"
            >
              {loading ? '…' : `${copy.enter} →`}
            </Button>

          </div>

        </div>
      </div>

      {/* ── Settings controls — fixed bottom-right ────────── */}
      <div className="fixed bottom-4 right-5 flex items-center gap-3 text-[10px] font-mono uppercase tracking-[0.15em] text-muted-foreground/50">
        {/* Language */}
        <div className="flex items-center gap-0.5">
          <Languages className="size-3 mr-1 text-muted-foreground/40" />
          {(['zh', 'en', 'ja'] as const).map(l => (
            <button
              key={l}
              onClick={() => setLang(l)}
              className={`px-1.5 py-0.5 rounded transition-colors ${lang === l ? 'bg-foreground text-background' : 'hover:text-foreground'}`}
            >
              {LANG_LABELS[l]}
            </button>
          ))}
        </div>

        {/* Dark/light */}
        <button
          onClick={() => setTheme(isDark ? 'light' : 'dark')}
          className="p-1 rounded hover:text-foreground transition-colors"
          aria-label="Toggle theme"
        >
          {isDark ? <Sun className="size-3" /> : <Moon className="size-3" />}
        </button>

        {/* Color scheme dots */}
        <div className="flex items-center gap-1">
          {THEMES.map(th => (
            <button
              key={th.id}
              title={th.label}
              onClick={() => setColorScheme(th.id)}
              className={`w-3 h-3 rounded-full border transition-all ${colorScheme === th.id ? 'border-foreground scale-110' : 'border-border hover:scale-105'}`}
              style={{ background: THEME_ACCENT_COLORS[th.id] }}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
