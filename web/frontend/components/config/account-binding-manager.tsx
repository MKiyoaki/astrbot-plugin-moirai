'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link2, RefreshCw, Trash2, X, Plus, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { useApp } from '@/lib/store'
import * as api from '@/lib/api'
import { cn } from '@/lib/utils'

type Lang = 'zh' | 'en' | 'ja'

const LABELS: Record<Lang, Record<string, string>> = {
  zh: {
    title: '账号绑定',
    description: '把同一个人的多个平台账号（如 QQ + Discord）绑定到一个用户名下，人格分析时合并看待。绑定可随时分离。',
    refresh: '刷新',
    createTitle: '新建绑定',
    createHint: '选择两个及以上账号，填写统一用户名后绑定。',
    selectAccounts: '选择账号',
    groupName: '用户名',
    groupNamePlaceholder: '为该用户起一个名字',
    bind: '绑定',
    noUngrouped: '没有可绑定的未分组账号。',
    groupsTitle: '已绑定分组',
    noGroups: '暂无绑定分组。',
    members: '成员',
    addMember: '加入账号',
    remove: '移出',
    dissolve: '解散分组',
    rename: '重命名',
    needSudo: '需要先开启 Sudo 模式。',
    bindOk: '绑定成功，正在后台重新合成人格。',
    unbindOk: '已移出，正在后台重新合成人格。',
    dissolveOk: '分组已解散。',
    renameOk: '已重命名。',
    failed: '操作失败',
    loadFailed: '加载失败',
    msgCount: '条消息',
    selectToAdd: '选择要加入的账号',
    confirmDissolve: '再次点击确认解散',
  },
  en: {
    title: 'Account Binding',
    description: 'Bind one person’s accounts across platforms (e.g. QQ + Discord) under one name so personality analysis treats them as one. Reversible anytime.',
    refresh: 'Refresh',
    createTitle: 'New Binding',
    createHint: 'Pick two or more accounts, name the unified user, then bind.',
    selectAccounts: 'Select accounts',
    groupName: 'User name',
    groupNamePlaceholder: 'Name this unified user',
    bind: 'Bind',
    noUngrouped: 'No unbound accounts available.',
    groupsTitle: 'Bound Groups',
    noGroups: 'No bound groups yet.',
    members: 'Members',
    addMember: 'Add account',
    remove: 'Remove',
    dissolve: 'Dissolve',
    rename: 'Rename',
    needSudo: 'Enable Sudo mode first.',
    bindOk: 'Bound. Re-synthesizing personality in the background.',
    unbindOk: 'Removed. Re-synthesizing personality in the background.',
    dissolveOk: 'Group dissolved.',
    renameOk: 'Renamed.',
    failed: 'Operation failed',
    loadFailed: 'Load failed',
    msgCount: 'msgs',
    selectToAdd: 'Select an account to add',
    confirmDissolve: 'Click again to confirm',
  },
  ja: {
    title: 'アカウント連携',
    description: '同一人物の複数プラットフォームのアカウント（QQ + Discord など）を一つの名前に紐づけ、人格分析でまとめて扱います。いつでも解除可能。',
    refresh: '更新',
    createTitle: '新規連携',
    createHint: '2つ以上のアカウントを選び、統一名を入力して連携します。',
    selectAccounts: 'アカウント選択',
    groupName: 'ユーザー名',
    groupNamePlaceholder: '統一ユーザー名を入力',
    bind: '連携',
    noUngrouped: '連携可能な未連携アカウントがありません。',
    groupsTitle: '連携済みグループ',
    noGroups: '連携グループはまだありません。',
    members: 'メンバー',
    addMember: 'アカウント追加',
    remove: '解除',
    dissolve: 'グループ解散',
    rename: '名前変更',
    needSudo: '先に Sudo モードを有効にしてください。',
    bindOk: '連携しました。バックグラウンドで人格を再合成中。',
    unbindOk: '解除しました。バックグラウンドで人格を再合成中。',
    dissolveOk: 'グループを解散しました。',
    renameOk: '名前を変更しました。',
    failed: '操作に失敗しました',
    loadFailed: '読み込み失敗',
    msgCount: '件',
    selectToAdd: '追加するアカウントを選択',
    confirmDissolve: 'もう一度クリックで確定',
  },
}

function identityText(b: api.BoundIdentity[]): string {
  return b.map(i => `${i.platform}:${i.physical_id}`).join(', ')
}

export function AccountBindingManager() {
  const { lang, sudo, toast } = useApp()
  const t = LABELS[(lang as Lang)] ?? LABELS.zh

  const [personas, setPersonas] = useState<api.HumanPersona[]>([])
  const [groups, setGroups] = useState<api.PersonaGroupItem[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [newName, setNewName] = useState('')
  const [renameDrafts, setRenameDrafts] = useState<Record<string, string>>({})
  const [addPick, setAddPick] = useState<Record<string, string>>({})
  const [confirmDissolve, setConfirmDissolve] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [p, g] = await Promise.all([
        api.personaGroups.listPersonas(),
        api.personaGroups.list(),
      ])
      setPersonas(p.items)
      setGroups(g.items)
    } catch {
      toast(t.loadFailed, 'destructive')
    } finally {
      setLoading(false)
    }
  }, [toast, t.loadFailed])

  useEffect(() => { load() }, [load])

  const ungrouped = useMemo(() => personas.filter(p => !p.group_id), [personas])

  const requireSudo = (): boolean => {
    if (!sudo) { toast(t.needSudo, 'destructive'); return false }
    return true
  }

  const reportError = (e: unknown) => {
    toast(`${t.failed}: ${(e as api.ApiError).body || ''}`, 'destructive')
  }

  const toggleSelect = (uid: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(uid)) next.delete(uid)
      else next.add(uid)
      return next
    })
  }

  const handleBind = async () => {
    if (!requireSudo()) return
    const uids = [...selected]
    if (uids.length < 2) return
    setBusy(true)
    try {
      await api.personaGroups.create(uids, newName.trim() || undefined)
      toast(t.bindOk)
      setSelected(new Set())
      setNewName('')
      await load()
    } catch (e) { reportError(e) } finally { setBusy(false) }
  }

  const handleAddMember = async (groupId: string) => {
    if (!requireSudo()) return
    const uid = addPick[groupId]
    if (!uid) return
    setBusy(true)
    try {
      await api.personaGroups.addMember(groupId, uid)
      toast(t.bindOk)
      setAddPick(prev => ({ ...prev, [groupId]: '' }))
      await load()
    } catch (e) { reportError(e) } finally { setBusy(false) }
  }

  const handleRemoveMember = async (uid: string) => {
    if (!requireSudo()) return
    setBusy(true)
    try {
      await api.personaGroups.removeMember('_', uid)
      toast(t.unbindOk)
      await load()
    } catch (e) { reportError(e) } finally { setBusy(false) }
  }

  const handleDissolve = async (groupId: string) => {
    if (!requireSudo()) return
    if (confirmDissolve !== groupId) { setConfirmDissolve(groupId); return }
    setConfirmDissolve(null)
    setBusy(true)
    try {
      await api.personaGroups.dissolve(groupId)
      toast(t.dissolveOk)
      await load()
    } catch (e) { reportError(e) } finally { setBusy(false) }
  }

  const handleRename = async (groupId: string, current: string) => {
    if (!requireSudo()) return
    const name = (renameDrafts[groupId] ?? '').trim()
    if (!name || name === current) return
    setBusy(true)
    try {
      await api.personaGroups.rename(groupId, name)
      toast(t.renameOk)
      await load()
    } catch (e) { reportError(e) } finally { setBusy(false) }
  }

  return (
    <Card className="overflow-hidden border-muted/60 shadow-sm">
      <CardHeader className="border-b border-border/50 pb-4">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-lg font-bold tracking-tight">
            <Link2 className="size-4" />
            {t.title}
          </CardTitle>
          <Button
            variant="ghost" size="sm" onClick={load}
            className="h-7 gap-1.5 px-2 text-xs text-muted-foreground hover:text-foreground"
          >
            <RefreshCw className={cn('size-3', loading && 'animate-spin')} />
            <span className="hidden sm:inline">{t.refresh}</span>
          </Button>
        </div>
        <CardDescription className="text-xs">{t.description}</CardDescription>
      </CardHeader>

      <CardContent className="flex flex-col gap-6 px-6 py-5">
        {/* Create binding */}
        <section className="flex flex-col gap-3">
          <div>
            <h3 className="text-sm font-semibold">{t.createTitle}</h3>
            <p className="text-xs text-muted-foreground">{t.createHint}</p>
          </div>

          {ungrouped.length === 0 ? (
            <p className="text-xs text-muted-foreground">{t.noUngrouped}</p>
          ) : (
            <div className="flex flex-col gap-2.5">
              <span className="text-xs text-muted-foreground">{t.selectAccounts}</span>
              <div className="grid gap-1.5 sm:grid-cols-2">
                {ungrouped.map(p => {
                  const on = selected.has(p.uid)
                  return (
                    <button
                      key={p.uid}
                      type="button"
                      onClick={() => toggleSelect(p.uid)}
                      className={cn(
                        'flex items-center gap-2 rounded-md border px-2.5 py-2 text-left transition-colors',
                        on ? 'border-primary bg-primary/5' : 'border-border hover:bg-muted/40',
                      )}
                    >
                      <span className={cn(
                        'flex size-4 shrink-0 items-center justify-center rounded border',
                        on ? 'border-primary bg-primary text-primary-foreground' : 'border-muted-foreground/40',
                      )}>
                        {on && <Check className="size-3" />}
                      </span>
                      <span className="flex min-w-0 flex-col">
                        <span className="truncate text-sm font-medium">{p.primary_name}</span>
                        <span className="truncate text-[10px] text-muted-foreground">
                          {identityText(p.bound_identities)} · {p.msg_count} {t.msgCount}
                        </span>
                      </span>
                    </button>
                  )
                })}
              </div>

              <div className="flex flex-wrap items-end gap-2">
                <div className="flex flex-1 flex-col gap-1.5 min-w-[180px]">
                  <span className="text-xs text-muted-foreground">{t.groupName}</span>
                  <Input
                    value={newName}
                    onChange={e => setNewName(e.target.value)}
                    placeholder={t.groupNamePlaceholder}
                    className="h-9 text-sm"
                  />
                </div>
                <Button
                  onClick={handleBind}
                  disabled={busy || selected.size < 2}
                  className="h-9"
                >
                  {busy && <Spinner data-icon="inline-start" />}
                  <Link2 className="size-3.5" />
                  {t.bind} {selected.size > 0 && `(${selected.size})`}
                </Button>
              </div>
            </div>
          )}
        </section>

        {/* Existing groups */}
        <section className="flex flex-col gap-3 border-t border-border/50 pt-5">
          <h3 className="text-sm font-semibold">{t.groupsTitle}</h3>
          {groups.length === 0 ? (
            <p className="text-xs text-muted-foreground">{t.noGroups}</p>
          ) : (
            <div className="flex flex-col gap-3">
              {groups.map(g => (
                <div key={g.group_id} className="rounded-lg border bg-muted/15 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Input
                      defaultValue={g.display_name}
                      onChange={e => setRenameDrafts(prev => ({ ...prev, [g.group_id]: e.target.value }))}
                      className="h-8 max-w-[200px] text-sm font-medium"
                    />
                    <Button
                      variant="outline" size="sm" className="h-8"
                      disabled={busy}
                      onClick={() => handleRename(g.group_id, g.display_name)}
                    >
                      {t.rename}
                    </Button>
                    <Badge variant="secondary" className="font-mono text-[10px]">
                      {g.members.length}
                    </Badge>
                    <div className="ml-auto">
                      <Button
                        variant={confirmDissolve === g.group_id ? 'destructive' : 'ghost'}
                        size="sm" className="h-8 gap-1.5 text-xs"
                        disabled={busy}
                        onClick={() => handleDissolve(g.group_id)}
                      >
                        <Trash2 className="size-3.5" />
                        {confirmDissolve === g.group_id ? t.confirmDissolve : t.dissolve}
                      </Button>
                    </div>
                  </div>

                  <div className="mt-2.5 flex flex-col gap-1.5">
                    <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{t.members}</span>
                    {g.members.map(m => (
                      <div key={m.uid} className="flex items-center gap-2 rounded-md bg-background/60 px-2.5 py-1.5">
                        <span className="flex min-w-0 flex-1 flex-col">
                          <span className="truncate text-sm">{m.primary_name}</span>
                          <span className="truncate text-[10px] text-muted-foreground">
                            {identityText(m.bound_identities)}
                          </span>
                        </span>
                        <Button
                          variant="ghost" size="sm"
                          className="h-7 gap-1 px-2 text-xs text-muted-foreground hover:text-destructive"
                          disabled={busy}
                          onClick={() => handleRemoveMember(m.uid)}
                        >
                          <X className="size-3.5" />
                          {t.remove}
                        </Button>
                      </div>
                    ))}
                  </div>

                  {ungrouped.length > 0 && (
                    <div className="mt-2.5 flex items-end gap-2">
                      <Select
                        value={addPick[g.group_id] ?? ''}
                        onValueChange={v => setAddPick(prev => ({ ...prev, [g.group_id]: v }))}
                      >
                        <SelectTrigger className="h-8 flex-1 text-xs">
                          <SelectValue placeholder={t.selectToAdd} />
                        </SelectTrigger>
                        <SelectContent>
                          {ungrouped.map(p => (
                            <SelectItem key={p.uid} value={p.uid}>
                              {p.primary_name} — {identityText(p.bound_identities)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Button
                        variant="outline" size="sm" className="h-8 gap-1.5"
                        disabled={busy || !addPick[g.group_id]}
                        onClick={() => handleAddMember(g.group_id)}
                      >
                        <Plus className="size-3.5" />
                        {t.addMember}
                      </Button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        {!sudo && (
          <p className="text-[11px] text-muted-foreground">{t.needSudo}</p>
        )}
      </CardContent>
    </Card>
  )
}
