'use client'

import { PageHeader } from '@/components/layout/page-header'
import { AccountBindingManager } from '@/components/config/account-binding-manager'
import { useApp } from '@/lib/store'

export default function BindingsPage() {
  const { lang } = useApp()
  const title = lang === 'zh' ? '账号绑定' : lang === 'ja' ? 'アカウント連携' : 'Account Binding'

  return (
    <div className="flex w-full flex-1 h-full flex-col min-w-0 overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-500 ease-out fill-mode-both">
      <PageHeader variant="loom" loomIssue="ΣΥΝΔΕΣΗ" title={title} />
      <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-6 min-w-0">
        <AccountBindingManager />
      </div>
    </div>
  )
}
