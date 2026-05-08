'use client'

import { useState, useMemo } from 'react'
import { RotateCcw, Download, Maximize2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Slider } from '@/components/ui/slider'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Badge } from '@/components/ui/badge'
import type { PersonaNode } from '@/lib/api'
import type { PhysicsParams, VisualParams, ViewMode } from '@/lib/graph-types'
import { useApp } from '@/lib/store'

interface ParamsPanelProps {
  physics: PhysicsParams
  visual: VisualParams
  onPhysics: <K extends keyof PhysicsParams>(key: K, val: PhysicsParams[K]) => void
  onVisual: <K extends keyof VisualParams>(key: K, val: VisualParams[K]) => void
  viewMode: ViewMode
  onViewMode: (mode: ViewMode) => void
  selectedMemberId: string | null
  onSelectedMemberId: (id: string | null) => void
  memberSort: string
  onMemberSort: (sort: string) => void
  groupNodes: PersonaNode[]
  onFocusNode: (id: string) => void
  onRefreshLayout: () => void
  svgEl?: SVGSVGElement | null
}

export function ParamsPanel({
  physics,
  visual,
  onPhysics,
  onVisual,
  viewMode,
  onViewMode,
  selectedMemberId,
  onSelectedMemberId,
  memberSort,
  onMemberSort,
  groupNodes,
  onFocusNode,
  onRefreshLayout,
  svgEl,
}: ParamsPanelProps) {
  const { i18n } = useApp()
  const t = i18n.graph.params
  const isCircular = physics.layoutMode === 'circular'
  const isLocked = physics.locked
  const physDisabled = isLocked || isCircular

  // Search state for node focus
  const [searchQ, setSearchQ] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)

  const searchResults = useMemo(() => {
    if (!searchQ.trim()) return []
    const q = searchQ.toLowerCase()
    return groupNodes.filter(n => n.data.label.toLowerCase().includes(q)).slice(0, 8)
  }, [searchQ, groupNodes])

  // Sorted member list for member mode
  const sortedMembers = useMemo(() => {
    const members = groupNodes.filter(n => !n.data.is_bot)
    return [...members].sort((a, b) => {
      const am = (a.data as { msg_count?: number }).msg_count ?? 0
      const bm = (b.data as { msg_count?: number }).msg_count ?? 0
      if (memberSort === 'msgs-desc') return bm - am
      if (memberSort === 'msgs-asc')  return am - bm
      if (memberSort === 'az') return a.data.label.localeCompare(b.data.label)
      if (memberSort === 'za') return b.data.label.localeCompare(a.data.label)
      return 0
    })
  }, [groupNodes, memberSort])

  const handleExportPng = () => {
    if (!svgEl) return
    const serializer = new XMLSerializer()
    const svgStr = serializer.serializeToString(svgEl)
    const blob = new Blob([svgStr], { type: 'image/svg+xml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'relation-graph.svg'
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleFullscreen = () => {
    const el = svgEl?.parentElement
    if (el?.requestFullscreen) el.requestFullscreen()
  }

  return (
    <div className="flex h-full flex-col overflow-hidden text-sm">
      {/* ── Fixed top section ───────────────────────────────────────────── */}
      <div className="shrink-0 border-b px-3 py-2.5 space-y-2.5">
        {/* Bot visibility */}
        <div className="flex items-center justify-between">
          <Label className="text-xs text-muted-foreground">{t.showBot}</Label>
          <Switch
            checked={visual.showBot}
            onCheckedChange={v => onVisual('showBot', v)}
          />
        </div>
        <Separator />

        {/* Lock layout */}
        <div className="flex items-center justify-between">
          <Label className="text-xs text-muted-foreground">{t.lockLayout}</Label>
          <Switch
            checked={physics.locked}
            onCheckedChange={v => onPhysics('locked', v)}
          />
        </div>
        <Separator />

        {/* Layout mode */}
        <div className="space-y-1">
          <Label className="text-xs text-muted-foreground">{t.layoutMode}</Label>
          <div className="flex gap-1">
            {(['circular', 'force'] as const).map(mode => (
              <Button
                key={mode}
                size="sm"
                variant={physics.layoutMode === mode ? 'default' : 'outline'}
                className="flex-1 text-xs h-7"
                onClick={() => onPhysics('layoutMode', mode)}
                disabled={isLocked}
              >
                {mode === 'circular' ? t.circular : t.force}
              </Button>
            ))}
          </div>
        </div>
        <Separator />

        {/* Display mode */}
        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">{t.displayMode}</Label>
          <div className="flex gap-1">
            {(['all', 'member'] as const).map(mode => (
              <Button
                key={mode}
                size="sm"
                variant={viewMode === mode ? 'default' : 'outline'}
                className="flex-1 text-xs h-7"
                onClick={() => onViewMode(mode)}
              >
                {mode === 'all' ? t.displayAll : t.displayMember}
              </Button>
            ))}
          </div>

          {viewMode === 'member' && (
            <div className="space-y-1.5 pt-1">
              <Select value={memberSort} onValueChange={v => onMemberSort(v ?? memberSort)}>
                <SelectTrigger className="h-7 text-xs">
                  <SelectValue placeholder={t.memberSort} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="msgs-desc">{t.memberSortMsgsDesc}</SelectItem>
                  <SelectItem value="msgs-asc">{t.memberSortMsgsAsc}</SelectItem>
                  <SelectItem value="az">{t.memberSortAZ}</SelectItem>
                  <SelectItem value="za">{t.memberSortZA}</SelectItem>
                </SelectContent>
              </Select>
              <Select
                value={selectedMemberId ?? ''}
                onValueChange={v => onSelectedMemberId(v || null)}
              >
                <SelectTrigger className="h-7 text-xs">
                  <SelectValue placeholder="选择成员…" />
                </SelectTrigger>
                <SelectContent>
                  {sortedMembers.map(n => (
                    <SelectItem key={n.data.id} value={n.data.id}>{n.data.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>
      </div>

      {/* ── Tab section ─────────────────────────────────────────────────── */}
      <Tabs defaultValue="phys" className="flex flex-1 flex-col overflow-hidden">
        <TabsList className="shrink-0 mx-2 mt-2 h-8 gap-0.5">
          <TabsTrigger value="phys" className="flex-1 text-xs h-7">{t.physTab}</TabsTrigger>
          <TabsTrigger value="visual" className="flex-1 text-xs h-7">{t.visualTab}</TabsTrigger>
          <TabsTrigger value="export" className="flex-1 text-xs h-7">{t.exportTab}</TabsTrigger>
        </TabsList>

        <ScrollArea className="flex-1">
          {/* ── Physics Tab ───────────────────────────────────────────── */}
          <TabsContent value="phys" className="mt-0 px-3 py-2 space-y-3">
            {/* Gravity source */}
            <ParamRow label={t.dataSrcGravity}>
              <Select
                value={physics.gravSource}
                onValueChange={v => onPhysics('gravSource', v as PhysicsParams['gravSource'])}
                disabled={physDisabled}
              >
                <SelectTrigger className="h-7 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="affinity">{t.srcAffinity}</SelectItem>
                  <SelectItem value="msgs">{t.srcMsgs}</SelectItem>
                  <SelectItem value="equal">{t.srcEqual}</SelectItem>
                </SelectContent>
              </Select>
            </ParamRow>

            {/* Edge width source */}
            <ParamRow label={t.dataSrcEdgeWidth}>
              <Select
                value={visual.edgeWidthSource}
                onValueChange={v => onVisual('edgeWidthSource', v as VisualParams['edgeWidthSource'])}
                disabled={isLocked}
              >
                <SelectTrigger className="h-7 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="equal">{t.srcEqual}</SelectItem>
                  <SelectItem value="affinity">{t.srcAffinity}</SelectItem>
                  <SelectItem value="msgs">{t.srcMsgs}</SelectItem>
                </SelectContent>
              </Select>
            </ParamRow>

            <Separator />

            {/* Bi-weight with tooltip */}
            <div className="space-y-1">
              <div className="flex items-center gap-1">
                <span className="text-xs text-muted-foreground flex-1">{t.biWeight}</span>
                <Tooltip>
                  <TooltipTrigger>
                    <Badge variant="outline" className="h-4 w-4 cursor-help text-[9px] p-0 flex items-center justify-center">?</Badge>
                  </TooltipTrigger>
                  <TooltipContent side="left" className="max-w-56 text-xs">{t.biWeightTip}</TooltipContent>
                </Tooltip>
                <span className="text-xs font-mono w-8 text-right">{physics.biWeight.toFixed(1)}</span>
              </div>
              <Slider
                min={1.0} max={2.0} step={0.05}
                value={[physics.biWeight]}
                onValueChange={v => onPhysics('biWeight', Array.isArray(v) ? v[0] : v)}
                disabled={isLocked}
              />
            </div>

            <Separator />
            <p className="text-xs text-muted-foreground font-medium">{t.physParams}</p>

            <SliderParam
              label={t.scalingRatio}
              value={physics.scalingRatio} min={0.1} max={15} step={0.1}
              disabled={physDisabled}
              onChange={v => onPhysics('scalingRatio', v)}
            />
            <SliderParam
              label={t.gravity}
              value={physics.gravity} min={0} max={5} step={0.1}
              disabled={physDisabled}
              onChange={v => onPhysics('gravity', v)}
            />
            <SliderParam
              label={t.edgeWeightInfluence}
              value={physics.edgeWeightInfluence} min={0} max={2} step={0.05}
              disabled={physDisabled}
              onChange={v => onPhysics('edgeWeightInfluence', v)}
            />
            <SliderParam
              label={t.damping}
              value={physics.damping} min={0.1} max={1} step={0.05}
              disabled={physDisabled}
              onChange={v => onPhysics('damping', v)}
            />
            <SliderParam
              label={t.iterations}
              value={physics.iterations} min={40} max={400} step={10}
              disabled={physDisabled}
              onChange={v => onPhysics('iterations', Math.round(v))}
            />

            <Separator />
            <p className="text-xs text-muted-foreground font-medium">{t.switches}</p>

            <SwitchRow label={t.preventOverlap} checked={physics.preventOverlap} disabled={physDisabled}
              onChange={v => onPhysics('preventOverlap', v)} />
            <SwitchRow label={t.linLog} checked={physics.linLog} disabled={physDisabled}
              onChange={v => onPhysics('linLog', v)} />
            <SwitchRow label={t.dissuadeHubs} checked={physics.dissuadeHubs} disabled={physDisabled}
              onChange={v => onPhysics('dissuadeHubs', v)} />

            <Button
              size="sm" variant="outline" className="w-full text-xs h-8"
              disabled={physDisabled}
              onClick={onRefreshLayout}
            >
              <RotateCcw className="mr-1.5 h-3 w-3" />
              {t.refreshLayout}
            </Button>
          </TabsContent>

          {/* ── Visual Tab ────────────────────────────────────────────── */}
          <TabsContent value="visual" className="mt-0 px-3 py-2 space-y-3">
            <p className="text-xs text-muted-foreground font-medium">{t.renderParams}</p>

            <SliderParam
              label={t.edgeOpacity}
              value={visual.edgeOpacity} min={0.05} max={1} step={0.05}
              onChange={v => onVisual('edgeOpacity', v)}
            />
            <SwitchRow label={t.showArrows} checked={visual.showArrows}
              onChange={v => onVisual('showArrows', v)} />
            {visual.showArrows && (
              <SliderParam
                label={t.arrowSize}
                value={visual.arrowSize} min={3} max={16} step={1}
                onChange={v => onVisual('arrowSize', v)}
              />
            )}

            <Separator />

            {/* Node search */}
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground font-medium">{t.searchNode}</p>
              <Popover open={searchOpen && searchResults.length > 0} onOpenChange={setSearchOpen}>
                <PopoverTrigger>
                  <Input
                    className="h-7 text-xs"
                    placeholder={t.searchPlaceholder}
                    value={searchQ}
                    onChange={e => { setSearchQ(e.target.value); setSearchOpen(true) }}
                  />
                </PopoverTrigger>
                <PopoverContent
                  className="w-[200px] p-1"
                  align="start"
                >
                  {searchResults.map(n => (
                    <button
                      key={n.data.id}
                      className="w-full text-left px-2 py-1 text-xs rounded hover:bg-accent"
                      onClick={() => {
                        onFocusNode(n.data.id)
                        setSearchQ('')
                        setSearchOpen(false)
                      }}
                    >
                      {n.data.label}
                    </button>
                  ))}
                </PopoverContent>
              </Popover>
            </div>

            <Separator />
            <p className="text-xs text-muted-foreground font-medium">{t.colorMapping}</p>

            {/* Leiden clustering */}
            <div className="space-y-2">
              <div className="flex items-center gap-1">
                <span className="text-xs text-muted-foreground flex-1">{t.leidenCluster}</span>
                <Switch
                  checked={visual.leidenEnabled}
                  onCheckedChange={v => onVisual('leidenEnabled', v)}
                />
              </div>
              {visual.leidenEnabled && (
                <div className="space-y-1">
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-muted-foreground flex-1">{t.leidenResolution}</span>
                    <Tooltip>
                      <TooltipTrigger>
                        <Badge variant="outline" className="h-4 w-4 cursor-help text-[9px] p-0 flex items-center justify-center">?</Badge>
                      </TooltipTrigger>
                      <TooltipContent side="left" className="max-w-56 text-xs">{t.leidenResolutionTip}</TooltipContent>
                    </Tooltip>
                    <span className="text-xs font-mono w-10 text-right">{visual.leidenResolution.toFixed(2)}</span>
                  </div>
                  <Slider
                    min={0.1} max={10} step={0.1}
                    value={[visual.leidenResolution]}
                    onValueChange={v => onVisual('leidenResolution', Array.isArray(v) ? v[0] : v)}
                  />
                </div>
              )}
            </div>

            {/* Sentiment color */}
            <SwitchRow label={t.sentimentColor} checked={visual.sentimentEnabled}
              onChange={v => onVisual('sentimentEnabled', v)} />

            {visual.sentimentEnabled && (
              <ParamRow label={t.sentimentAxis}>
                <Select
                  value={visual.sentimentAxis}
                  onValueChange={v => onVisual('sentimentAxis', v as VisualParams['sentimentAxis'])}
                >
                  <SelectTrigger className="h-7 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="benevolence">{t.axisBenevolence}</SelectItem>
                    <SelectItem value="power">{t.axisPower}</SelectItem>
                  </SelectContent>
                </Select>
              </ParamRow>
            )}

            <Button size="sm" variant="outline" className="w-full text-xs h-8"
              onClick={() => {
                onVisual('leidenEnabled', false)
                onVisual('sentimentEnabled', true)
              }}
            >
              <RotateCcw className="mr-1.5 h-3 w-3" />
              {t.resetColors}
            </Button>
          </TabsContent>

          {/* ── Export Tab ────────────────────────────────────────────── */}
          <TabsContent value="export" className="mt-0 px-3 py-2 space-y-3">
            <p className="text-xs text-muted-foreground font-medium">{t.perfControl}</p>
            <SwitchRow label={t.highFps} checked={false} onChange={() => {}} />
            <SwitchRow label={t.webgl} checked={false} onChange={() => {}} />
            <Separator />
            <Button size="sm" variant="outline" className="w-full text-xs h-8" onClick={handleExportPng}>
              <Download className="mr-1.5 h-3 w-3" />
              {t.exportPng}
            </Button>
            <Button size="sm" variant="outline" className="w-full text-xs h-8" onClick={handleFullscreen}>
              <Maximize2 className="mr-1.5 h-3 w-3" />
              {t.fullscreen}
            </Button>
          </TabsContent>
        </ScrollArea>
      </Tabs>
    </div>
  )
}

// ── Internal helper components ────────────────────────────────────────────────

function ParamRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      {children}
    </div>
  )
}

function SliderParam({
  label, value, min, max, step, disabled = false, onChange,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  disabled?: boolean
  onChange: (v: number) => void
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center">
        <span className="text-xs text-muted-foreground flex-1">{label}</span>
        <span className="text-xs font-mono w-10 text-right">{value % 1 === 0 ? value : value.toFixed(2)}</span>
      </div>
      <Slider
        min={min} max={max} step={step}
        value={[value]}
        onValueChange={v => onChange(Array.isArray(v) ? v[0] : v)}
        disabled={disabled}
      />
    </div>
  )
}

function SwitchRow({
  label, checked, disabled = false, onChange,
}: {
  label: string
  checked: boolean
  disabled?: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <div className="flex items-center justify-between">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <Switch checked={checked} onCheckedChange={onChange} disabled={disabled} />
    </div>
  )
}
