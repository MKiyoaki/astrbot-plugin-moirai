'use client'

import { useState } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { Check, Minus, Lock, ChevronRight } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useApp } from '@/lib/store'
import { LLM_FEATURE_CONFIG_KEY, type LlmFeatureKey } from '@/lib/llm-budget'

/** 进度条颜色随档位变化，给用户「负载偏高」的直觉。 */
function barColor(percent: number): string {
  if (percent < 60) return 'bg-emerald-500'
  if (percent <= 85) return 'bg-primary'
  return 'bg-amber-500'
}

/**
 * LLM 用量估算徽标 — 侧栏左下角、sudo 按钮上方。
 * 显示按功能权重粗估的 LLM 负载（细进度条），点击弹出功能清单；
 * 点击清单中的功能项可跳转到插件配置页对应开关。
 */
export function LlmBudgetBadge() {
  const { i18n, llmBudget } = useApp()
  const router = useRouter()
  const pathname = usePathname()
  const [open, setOpen] = useState(false)

  if (!llmBudget.loaded) return null

  const { percent, features } = llmBudget
  const t = i18n.llmBudget

  /** 跳转到插件配置页并定位到该功能对应的配置项（居中）。 */
  const jumpToConfig = (key: LlmFeatureKey) => {
    const configKey = LLM_FEATURE_CONFIG_KEY[key]
    if (!configKey) return // extraction — 常驻功能无开关
    const target = `cfg-${configKey}`
    setOpen(false)
    // sessionStorage 兜底：无论是否需要导航都写入，配置页加载时会消费它
    try {
      sessionStorage.setItem('em_config_scroll_target', target)
    } catch {}
    // 已在配置页（注意 next.config trailingSlash → pathname 形如 "/config/"）
    // 直接派发滚动定位事件；否则导航过去由 sessionStorage 触发定位。
    const onConfigPage = pathname.replace(/\/+$/, '') === '/config'
    if (onConfigPage) {
      window.dispatchEvent(new CustomEvent('em_config_scroll_target', { detail: target }))
    } else {
      router.push('/config')
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          title={t.hint}
          className="group-data-[collapsible=icon]:hidden w-full cursor-pointer rounded-md px-3 py-2 text-left transition-colors hover:bg-accent/50"
        >
          <span className="block truncate text-[9px] font-mono uppercase tracking-[0.18em] text-muted-foreground/60">
            {t.title}
          </span>
          <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div
              className={`h-full ${barColor(percent)} transition-all`}
              style={{ width: `${percent}%` }}
            />
          </div>
        </button>
      </PopoverTrigger>
      <PopoverContent side="right" align="end" className="w-64 p-2">
        <p className="mb-1.5 px-1 text-[10px] leading-snug text-muted-foreground/70">
          {t.hint}
        </p>
        <div className="space-y-0.5">
          {features.map(f => {
            const label = t[f.key as LlmFeatureKey]
            const clickable = LLM_FEATURE_CONFIG_KEY[f.key] !== null
            const icon = f.always ? (
              <Lock className="size-3.5 shrink-0 text-muted-foreground/70" />
            ) : f.enabled ? (
              <Check className="size-3.5 shrink-0 text-emerald-600" />
            ) : (
              <Minus className="size-3.5 shrink-0 text-muted-foreground/40" />
            )
            return (
              <button
                key={f.key}
                type="button"
                disabled={!clickable}
                onClick={() => jumpToConfig(f.key)}
                className={
                  'flex w-full items-center gap-2 rounded px-2 py-1 text-left text-xs transition-colors ' +
                  (clickable ? 'cursor-pointer hover:bg-accent' : 'cursor-default')
                }
              >
                {icon}
                <span className={f.enabled ? '' : 'text-muted-foreground/50 line-through'}>
                  {label}
                </span>
                <span className="ml-auto text-[9px] font-mono uppercase tracking-wider text-muted-foreground/60">
                  {f.always ? t.always : f.enabled ? t.enabled : t.disabled}
                </span>
                {clickable && (
                  <ChevronRight className="size-3 shrink-0 text-muted-foreground/40" />
                )}
              </button>
            )
          })}
        </div>
        <p className="mt-1.5 px-1 text-[9px] leading-snug text-muted-foreground/50">
          {t.jumpHint}
        </p>
      </PopoverContent>
    </Popover>
  )
}
