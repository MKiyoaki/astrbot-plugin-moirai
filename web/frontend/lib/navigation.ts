'use client'

const ROUTES = new Set([
  '/',
  '/events',
  '/graph',
  '/summary',
  '/recall',
  '/stats',
  '/library',
  '/config',
  '/settings',
])

const BASE_PATH = '/api/pages/astrbot_plugin_moirai/moirai'

function isIframeEmbed() {
  if (typeof window === 'undefined') return false
  if (window.AstrBotPluginPage) return true
  try {
    return window.self !== window.top
  } catch {
    return true
  }
}

function currentRouteDepth() {
  if (typeof window === 'undefined') return 0
  const pathname = window.location.pathname.replace(/\/index\.html$/, '/')
  // Strip basePath prefix then count remaining segments
  const stripped = BASE_PATH ? pathname.replace(BASE_PATH, '') : pathname
  const tail = stripped.replace(/^\/|\/$/g, '')
  return tail ? tail.split('/').filter(Boolean).length : 0
}

export function pageHref(route: string) {
  const normalized = route === '/' ? '/' : `/${route.replace(/^\/|\/$/g, '')}`
  if (!ROUTES.has(normalized)) return route

  // Inside AstrBot iframe: use relative paths (asset_token forwarding requires it)
  if (isIframeEmbed()) {
    const prefix = currentRouteDepth() > 0 ? '../'.repeat(currentRouteDepth()) : './'
    if (normalized === '/') return prefix
    return `${prefix}${normalized.slice(1)}/`
  }

  // Self-hosted server or direct browser access: absolute path with basePath prefix
  if (normalized === '/') return `${BASE_PATH}/`
  return `${BASE_PATH}${normalized}/`
}

export function goToPage(route: string) {
  if (typeof window === 'undefined') return
  window.location.assign(pageHref(route))
}

export function routeIsActive(pathname: string | null, route: string) {
  // usePathname() returns path WITHOUT basePath prefix, so compare directly
  const normalized = route === '/' ? '/' : `/${route.replace(/^\/|\/$/g, '')}`
  if (normalized === '/') return pathname === '/'
  return Boolean(pathname?.includes(normalized))
}
