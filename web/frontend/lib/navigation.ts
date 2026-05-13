'use client'

export function routeIsActive(pathname: string | null, route: string) {
  const normalized = route === '/' ? '/' : `/${route.replace(/^\/|\/$/g, '')}`
  if (normalized === '/') return pathname === '/'
  return Boolean(pathname?.includes(normalized))
}
