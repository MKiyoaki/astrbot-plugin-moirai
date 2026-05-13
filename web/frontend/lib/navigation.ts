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

function isPluginPage() {
  return typeof window !== 'undefined' && Boolean(window.AstrBotPluginPage)
}

function currentRouteDepth() {
  if (typeof window === 'undefined') return 0
  const pathname = window.location.pathname.replace(/\/index\.html$/, '/')
  const match = pathname.match(/\/moirai(?:\/(.+?))?\/?$/)
  const tail = match?.[1] ?? ''
  return tail ? tail.split('/').filter(Boolean).length : 0
}

export function pageHref(route: string) {
  const normalized = route === '/' ? '/' : `/${route.replace(/^\/|\/$/g, '')}`
  if (!ROUTES.has(normalized)) return route
  if (!isPluginPage()) return normalized

  const prefix = currentRouteDepth() > 0 ? '../'.repeat(currentRouteDepth()) : './'
  if (normalized === '/') return prefix
  return `${prefix}${normalized.slice(1)}/`
}

export function goToPage(route: string) {
  if (typeof window === 'undefined') return
  window.location.assign(pageHref(route))
}

export function routeIsActive(pathname: string | null, route: string) {
  const normalized = route === '/' ? '/' : `/${route.replace(/^\/|\/$/g, '')}`
  if (normalized === '/') return pathname === '/'
  return Boolean(pathname?.includes(normalized))
}
