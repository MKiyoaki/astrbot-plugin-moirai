'use client'

type StorageKind = 'local' | 'session'

function storage(kind: StorageKind): Storage | null {
  if (typeof window === 'undefined') return null
  try {
    return kind === 'local' ? window.localStorage : window.sessionStorage
  } catch {
    return null
  }
}

export function getStored(key: string, fallback: string | null = null, kind: StorageKind = 'local') {
  try {
    return storage(kind)?.getItem(key) ?? fallback
  } catch {
    return fallback
  }
}

export function setStored(key: string, value: string, kind: StorageKind = 'local') {
  try {
    storage(kind)?.setItem(key, value)
  } catch {}
}

export function removeStored(key: string, kind: StorageKind = 'local') {
  try {
    storage(kind)?.removeItem(key)
  } catch {}
}
