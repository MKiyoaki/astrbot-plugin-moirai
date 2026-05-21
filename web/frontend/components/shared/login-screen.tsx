'use client'

import { useState, useEffect } from 'react'
import { useTheme } from 'next-themes'
import { Eye, EyeOff, Moon, Sun, Monitor, Languages, Loader2, AlertCircle } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { useApp } from '@/lib/store'
import { getStored, setStored } from '@/lib/safe-storage'
import * as api from '@/lib/api'
import { SilkThreadBg } from '@/components/shared/silk-thread-bg'

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
  const { theme, setTheme } = useTheme()

  const [password, setPassword] = useState('')
  const [showPwd, setShowPwd] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  // Speed up the silk animation while the password field is focused.
  const [passwordFocused, setPasswordFocused] = useState(false)

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
      verifying: '验证中…',
      tagline: <>为 AstrBot 注入<span style={{ color: 'var(--color-primary, oklch(0.53 0.130 295))' }}>持久记忆</span>，<br />让对话跨越时间。</>,
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
      verifying: 'Verifying…',
      tagline: <>Inject <span style={{ color: 'var(--color-primary, oklch(0.53 0.130 295))' }}>persistent memory</span> into AstrBot,<br />so conversations transcend time.</>,
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
      verifying: '認証中…',
      tagline: <>AstrBot に<span style={{ color: 'var(--color-primary, oklch(0.53 0.130 295))' }}>永続記憶</span>を宿し、<br />対話を時を超えてつなぐ。</>,
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
          <SilkThreadBg variant="login" fast={passwordFocused} />

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
            <h1 className="font-serif text-6xl font-bold tracking-tight leading-none mb-6 transition-transform duration-500 ease-out hover:-translate-y-0.5">
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
        <div className="flex-1 flex flex-col justify-between p-8 md:p-12 max-w-lg mx-auto w-full relative">
          {/* Radial halo behind form — subtle primary tint, intensifies when input is focused */}
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 transition-opacity duration-700 ease-out"
            style={{
              background: 'radial-gradient(ellipse at center, color-mix(in srgb, var(--color-primary, oklch(0.53 0.130 295)) 7%, transparent) 0%, transparent 62%)',
              opacity: passwordFocused ? 1 : 0.55,
            }}
          />
          {/* Form top label */}
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground/50 mb-8 relative">
            {copy.enterArchive}
          </div>

          {/* Form body */}
          <div className="flex-1 flex flex-col justify-center gap-6 relative">
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
                  onFocus={() => setPasswordFocused(true)}
                  onBlur={() => setPasswordFocused(false)}
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
                <div
                  key={error}
                  className="animate-in slide-in-from-top-2 fade-in duration-300 flex items-center gap-1.5 text-xs text-destructive font-mono tracking-wide"
                >
                  <AlertCircle className="size-3 shrink-0 animate-pulse" />
                  <span>{error}</span>
                </div>
              )}
            </div>

            {/* Submit */}
            <Button
              onClick={submit}
              disabled={loading || !password}
              className="w-full rounded-none h-12 font-mono text-sm uppercase tracking-[0.15em] transition-all duration-200 disabled:opacity-60 active:scale-[0.99]"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="size-3.5 animate-spin" />
                  {copy.verifying}
                </span>
              ) : (
                `${copy.enter} →`
              )}
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

        {/* Dark/light/system */}
        <div className="flex items-center gap-0.5">
          {([
            { value: 'light',  icon: <Sun className="size-3" /> },
            { value: 'dark',   icon: <Moon className="size-3" /> },
            { value: 'system', icon: <Monitor className="size-3" /> },
          ] as const).map(opt => (
            <button
              key={opt.value}
              onClick={() => setTheme(opt.value)}
              className={`p-1 rounded transition-colors ${theme === opt.value ? 'bg-foreground text-background' : 'hover:text-foreground'}`}
            >
              {opt.icon}
            </button>
          ))}
        </div>

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
