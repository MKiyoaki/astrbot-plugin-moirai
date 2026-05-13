'use client'

/**
 * Runtime diagnostics for debugging WebUI deployment contexts.
 * Call window.__moiraiDebug() in the browser console to get a full report.
 * Works in all three contexts: run_webui_dev, self-hosted WebuiServer, AstrBot Plugin Pages.
 */

interface DebugReport {
  context: 'iframe-astrbot' | 'selfhosted' | 'unknown'
  url: string
  pathname: string
  bridge: {
    present: boolean
    hasApiGet: boolean
    hasApiPost: boolean
    context: unknown
  }
  assetTest: {
    sampleHref: string | null
    hasAssetToken: boolean
    hasAbsoluteNext: boolean
  }
  apiTest: Record<string, { status: number | string; ok: boolean }>
}

async function _runApiTest(url: string): Promise<{ status: number | string; ok: boolean }> {
  try {
    const r = await fetch(url, { credentials: 'same-origin' })
    return { status: r.status, ok: r.ok }
  } catch (e) {
    return { status: String(e), ok: false }
  }
}

export async function collectDebugReport(): Promise<DebugReport> {
  const bridge = (window as unknown as { AstrBotPluginPage?: Record<string, unknown> }).AstrBotPluginPage
  let isIframe = false
  try { isIframe = window.self !== window.top } catch { isIframe = true }

  const context: DebugReport['context'] = bridge
    ? 'iframe-astrbot'
    : isIframe ? 'iframe-astrbot' : 'selfhosted'

  // Check a sample link href in the page for asset_token
  const sampleLink = document.querySelector<HTMLLinkElement>('link[href*="_next"]')
  const sampleHref = sampleLink?.href ?? null
  const hasAssetToken = sampleHref?.includes('asset_token') ?? false
  const hasAbsoluteNext = sampleHref?.includes('/_next/') ?? false

  // API tests
  const apiUrls = ['/api/stats', '/api/auth/status']
  const apiTest: DebugReport['apiTest'] = {}
  for (const url of apiUrls) {
    apiTest[url] = await _runApiTest(url)
  }

  let bridgeCtx: unknown = null
  if (bridge && typeof bridge.getContext === 'function') {
    bridgeCtx = bridge.getContext()
  }

  return {
    context,
    url: window.location.href,
    pathname: window.location.pathname,
    bridge: {
      present: !!bridge,
      hasApiGet: typeof bridge?.apiGet === 'function',
      hasApiPost: typeof bridge?.apiPost === 'function',
      context: bridgeCtx,
    },
    assetTest: { sampleHref, hasAssetToken, hasAbsoluteNext },
    apiTest,
  }
}

export function installDebugGlobal() {
  if (typeof window === 'undefined') return
  ;(window as unknown as Record<string, unknown>).__moiraiDebug = async () => {
    const report = await collectDebugReport()
    console.group('%c[Moirai Debug Report]', 'font-weight:bold;color:#7c3aed')
    console.log('Context:', report.context)
    console.log('URL:', report.url)
    console.log('Bridge:', report.bridge)
    console.log('Asset token check:', report.assetTest)
    console.log('API tests:', report.apiTest)

    const issues: string[] = []
    if (report.assetTest.hasAbsoluteNext) issues.push('⚠ Absolute /_next/ paths found — AstrBot cannot inject asset_token')
    if (!report.assetTest.hasAssetToken && report.context === 'iframe-astrbot') issues.push('⚠ No asset_token on _next/ links — CSS/JS will 401')
    if (!report.bridge.present && report.context === 'iframe-astrbot') issues.push('⚠ AstrBotPluginPage bridge not found in iframe')
    Object.entries(report.apiTest).forEach(([url, res]) => {
      if (!res.ok && res.status !== 401) issues.push(`⚠ API ${url} → ${res.status}`)
    })

    if (issues.length) {
      console.group('%cIssues found', 'color:red')
      issues.forEach(i => console.warn(i))
      console.groupEnd()
    } else {
      console.log('%c✓ No issues detected', 'color:green')
    }
    console.groupEnd()
    return report
  }
  console.debug('[Moirai] Debug tool ready — run window.__moiraiDebug() for diagnostics')
}
