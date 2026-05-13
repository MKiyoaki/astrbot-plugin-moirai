'use client'

import { useEffect } from 'react'
import { installDebugGlobal } from '@/lib/debug'

/** Installs window.__moiraiDebug() on mount. Renders nothing. */
export function DebugInstaller() {
  useEffect(() => {
    installDebugGlobal()
  }, [])
  return null
}
