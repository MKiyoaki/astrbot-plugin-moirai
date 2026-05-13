'use client'

import { useEffect } from 'react'

interface LoginScreenProps {
  onSuccess: () => void
}

export function LoginScreen({ onSuccess }: LoginScreenProps) {
  useEffect(() => {
    onSuccess()
  }, [onSuccess])

  return null
}
