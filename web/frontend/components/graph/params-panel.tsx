'use client'

import { useState, useMemo } from 'react'
import { RotateCcw, Download, Maximize2, Trash2, FlaskConical, Wand2, Image as ImageIcon, FileSpreadsheet, Share2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Badge } from '@/components/ui/badge'
import { NumberField } from '@/components/graph/number-field'
import type { PersonaNode } from '@/lib/api'
import type { PhysicsParams, VisualParams, ViewMode } from '@/lib/graph-types'
import { useApp } from '@/lib/store'

export type GraphExportFormat = 'gexf' | 'csv' | 'svg' | 'png'

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
  onAutoSettings: () => void
  onExport: (format: GraphExportFormat, options: { scale: number; transparent: boolean }) => void
  svgEl?: SVGSVGElement | null
  groupName?: string
  onClearScope?: () => void
  canClearScope?: boolean
  sudoMode?: boolean
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
  onAutoSettings,
  onExport,
  svgEl,
  onClearScope,
  canClearScope = false,
  sudoMode = false,
}: ParamsPanelProps) {
  const { i18n } = useApp()
  const t = i18n.graph.params
  const isCircular = physics.layoutMode === 'circular'
  const isLocked = physics.locked
  const physDisabled = isLocked || isCircular

  // Search state for node focus
  const [searchQ, setSearchQ] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)

  // Export options
  const [pngScale, setPngScale] = useState(2)
  const [transparent, setTransparent] = useState(false)

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

  const handleFullscreen = () => {
    const el = svgEl?.parentElement
    if (el?.requestFullscreen) el.requestFullscreen()
  }

  const exportOptions = { scale: pngScale, transparent }

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
            {(['circular', 'force'] as const).map(mode => {
              const btn = (
                <Button
                  key={mode}
                  size="sm"
                  variant={physics.layoutMode === mode ? 'default' : 'outline'}
                  className="flex-1 text-xs h-7"
                  onClick={() => onPhysics('layoutMode', mode)}
                  disabled={isLocked}
                >
                  {mode === 'circular' ? (
                    t.circular
                  ) : (
                    <span className="flex items-center justify-center gap-1">
                      {t.force}
                      <FlaskConical className="size-3 text-amber-500" />
                    </span>
                  )}
                </Button>
              )
              if (mode !== 'force') return btn
              // 力导向为实验性布局 — 与 Soul Layer 一致打实验标记
              return (
                <Tooltip key={mode}>
                  <TooltipTrigger asChild>{btn}</TooltipTrigger>
                  <TooltipContent className="max-w-[220px] text-xs leading-relaxed">
                    {(t as Record<string, string>).forceExperimental}
                  </TooltipContent>
                </Tooltip>
              )
            })}
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
                  <SelectValue placeholder={t.memberPlaceholder} />
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
          {/* ── Physics Tab — Gephi ForceAtlas2 ───────────────────────── */}
          <TabsContent value="phys" className="mt-0 px-3 py-2 space-y-3">
            <Button
              size="sm" variant="secondary" className="w-full text-xs h-8"
              disabled={physDisabled}
              onClick={onAutoSettings}
            >
              <Wand2 className="mr-1.5 h-3 w-3" />
              {t.autoSettings}
            </Button>
            <p className="text-muted-foreground text-[11px] leading-relaxed">
              {t.autoSettingsTip}
            </p>

            <Separator />
            <SectionTitle disabled={physDisabled}>{t.groupTuning}</SectionTitle>

            <NumberField
              label={t.scalingRatio} value={physics.scalingRatio}
              min={0} step={0.1} disabled={physDisabled}
              onChange={v => onPhysics('scalingRatio', v)} tooltip={t.scalingRatioTip}
            />
            <SwitchRow label={t.strongGravityMode} checked={physics.strongGravityMode}
              disabled={physDisabled} onChange={v => onPhysics('strongGravityMode', v)}
              tooltip={t.strongGravityModeTip} />
            <NumberField
              label={t.gravity} value={physics.gravity}
              min={0} step={0.1} disabled={physDisabled}
              onChange={v => onPhysics('gravity', v)} tooltip={t.gravityTip}
            />

            <Separator />
            <SectionTitle disabled={physDisabled}>{t.groupBehavior}</SectionTitle>

            <SwitchRow label={t.dissuadeHubs} checked={physics.outboundAttractionDistribution}
              disabled={physDisabled} onChange={v => onPhysics('outboundAttractionDistribution', v)}
              tooltip={t.dissuadeHubsTip} />
            <SwitchRow label={t.linLog} checked={physics.linLogMode}
              disabled={physDisabled} onChange={v => onPhysics('linLogMode', v)}
              tooltip={t.linLogTip} />
            <SwitchRow label={t.preventOverlap} checked={physics.adjustSizes}
              disabled={physDisabled} onChange={v => onPhysics('adjustSizes', v)}
              tooltip={t.preventOverlapTip} />
            <NumberField
              label={t.edgeWeightInfluence} value={physics.edgeWeightInfluence}
              min={0} step={0.1} disabled={physDisabled}
              onChange={v => onPhysics('edgeWeightInfluence', v)} tooltip={t.edgeWeightInfluenceTip}
            />

            <Separator />
            <SectionTitle disabled={physDisabled}>{t.groupPerformance}</SectionTitle>

            <NumberField
              label={t.jitterTolerance} value={physics.jitterTolerance}
              min={0} step={0.1} disabled={physDisabled}
              onChange={v => onPhysics('jitterTolerance', v)} tooltip={t.jitterToleranceTip}
            />
            <SwitchRow label={t.barnesHutOptimize} checked={physics.barnesHutOptimize}
              disabled={physDisabled} onChange={v => onPhysics('barnesHutOptimize', v)}
              tooltip={t.barnesHutOptimizeTip} />
            <NumberField
              label={t.barnesHutTheta} value={physics.barnesHutTheta}
              min={0} step={0.1} disabled={physDisabled || !physics.barnesHutOptimize}
              onChange={v => onPhysics('barnesHutTheta', v)} tooltip={t.barnesHutThetaTip}
            />

            <Separator />
            <SectionTitle disabled={isLocked}>{t.groupMoirai}</SectionTitle>

            <NumberField
              label={t.iterations} value={physics.iterations}
              min={1} max={5000} step={10} integer disabled={physDisabled}
              onChange={v => onPhysics('iterations', v)} tooltip={t.iterationsTip}
            />
            <ParamRow label={t.dataSrcWeight} disabled={isLocked}>
              <Select
                value={physics.edgeWeightSource}
                onValueChange={v => onPhysics('edgeWeightSource', v as PhysicsParams['edgeWeightSource'])}
                disabled={isLocked}
              >
                <SelectTrigger className="h-7 text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="affinity">{t.srcAffinity}</SelectItem>
                  <SelectItem value="msgs">{t.srcMsgs}</SelectItem>
                  <SelectItem value="equal">{t.srcEqual}</SelectItem>
                </SelectContent>
              </Select>
            </ParamRow>
            <NumberField
              label={t.biWeight} value={physics.biWeight}
              min={1} step={0.05} disabled={isLocked}
              onChange={v => onPhysics('biWeight', v)} tooltip={t.biWeightTip}
            />

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
            <SectionTitle>{t.renderParams}</SectionTitle>

            <NumberField
              label={t.edgeOpacity} value={visual.edgeOpacity}
              min={0.05} max={1} step={0.05}
              onChange={v => onVisual('edgeOpacity', v)}
            />
            <NumberField
              label={t.defaultEdgeWidth} value={visual.defaultEdgeWidth}
              min={0.1} step={0.1}
              onChange={v => onVisual('defaultEdgeWidth', v)}
            />
            <ParamRow label={t.dataSrcEdgeWidth}>
              <Select
                value={visual.edgeWidthSource}
                onValueChange={v => onVisual('edgeWidthSource', v as VisualParams['edgeWidthSource'])}
              >
                <SelectTrigger className="h-7 text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="equal">{t.srcEqual}</SelectItem>
                  <SelectItem value="affinity">{t.srcAffinity}</SelectItem>
                  <SelectItem value="msgs">{t.srcMsgs}</SelectItem>
                </SelectContent>
              </Select>
            </ParamRow>
            <SwitchRow label={t.showArrows} checked={visual.showArrows}
              onChange={v => onVisual('showArrows', v)} />
            {visual.showArrows && (
              <NumberField
                label={t.arrowSize} value={visual.arrowSize}
                min={1} step={1} integer
                onChange={v => onVisual('arrowSize', v)}
              />
            )}

            <Separator />
            <SectionTitle>{t.labelParams}</SectionTitle>
            <SwitchRow label={t.alwaysShowLabels} checked={visual.alwaysShowLabels}
              onChange={v => onVisual('alwaysShowLabels', v)} tooltip={t.alwaysShowLabelsTip} />
            <NumberField
              label={t.labelFontSize} value={visual.labelFontSize}
              min={4} step={1} integer
              onChange={v => onVisual('labelFontSize', v)}
            />
            <SwitchRow label={t.showEdgeLabels} checked={visual.showEdgeLabels}
              onChange={v => onVisual('showEdgeLabels', v)} />
            {visual.showEdgeLabels && (
              <NumberField
                label={t.fontSize} value={visual.edgeLabelFontSize}
                min={4} step={1} integer
                onChange={v => onVisual('edgeLabelFontSize', v)}
              />
            )}

            <Separator />

            {/* Node search */}
            <div className="space-y-1">
              <SectionTitle>{t.searchNode}</SectionTitle>
              <Popover open={searchOpen && searchResults.length > 0} onOpenChange={setSearchOpen}>
                <PopoverTrigger asChild>
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
            <SectionTitle>{t.colorMapping}</SectionTitle>

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
                <NumberField
                  label={t.leidenResolution} value={visual.leidenResolution}
                  min={0.01} step={0.1}
                  onChange={v => onVisual('leidenResolution', v)}
                  tooltip={t.leidenResolutionTip}
                />
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
            <SectionTitle>{t.exportData}</SectionTitle>
            <p className="text-muted-foreground text-[11px] leading-relaxed">
              {t.exportDataTip}
            </p>
            <Button size="sm" variant="outline" className="w-full text-xs h-8"
              onClick={() => onExport('gexf', exportOptions)}>
              <Share2 className="mr-1.5 h-3 w-3" />
              {t.exportGexf}
            </Button>
            <Button size="sm" variant="outline" className="w-full text-xs h-8"
              onClick={() => onExport('csv', exportOptions)}>
              <FileSpreadsheet className="mr-1.5 h-3 w-3" />
              {t.exportCsv}
            </Button>

            <Separator />
            <SectionTitle>{t.exportImage}</SectionTitle>
            <p className="text-muted-foreground text-[11px] leading-relaxed">
              {t.exportImageTip}
            </p>
            <NumberField
              label={t.pngScale} value={pngScale}
              min={1} max={8} step={1} integer
              onChange={setPngScale}
            />
            <SwitchRow label={t.transparentBg} checked={transparent} onChange={setTransparent} />
            <Button size="sm" variant="outline" className="w-full text-xs h-8"
              onClick={() => onExport('png', exportOptions)}>
              <ImageIcon className="mr-1.5 h-3 w-3" />
              {t.exportPng}
            </Button>
            <Button size="sm" variant="outline" className="w-full text-xs h-8"
              onClick={() => onExport('svg', exportOptions)}>
              <Download className="mr-1.5 h-3 w-3" />
              {t.exportSvg}
            </Button>
            <Button size="sm" variant="outline" className="w-full text-xs h-8" onClick={handleFullscreen}>
              <Maximize2 className="mr-1.5 h-3 w-3" />
              {t.fullscreen}
            </Button>

            <Separator />
            <Button
              size="sm"
              variant="destructive"
              className="w-full text-xs h-8"
              disabled={!sudoMode || !canClearScope || !onClearScope}
              onClick={onClearScope}
            >
              <Trash2 className="mr-1.5 h-3 w-3" />
              {t.clearScopeImpressions}
            </Button>
          </TabsContent>
        </ScrollArea>
      </Tabs>
    </div>
  )
}

// ── Internal helper components ────────────────────────────────────────────────

function SectionTitle({ children, disabled = false }: { children: React.ReactNode; disabled?: boolean }) {
  return (
    <p className={`text-xs text-muted-foreground font-medium ${disabled ? 'opacity-50' : ''}`}>
      {children}
    </p>
  )
}

function ParamRow({ label, children, disabled = false }: { label: string; children: React.ReactNode, disabled?: boolean }) {
  return (
    <div className={`space-y-1 ${disabled ? 'opacity-50 grayscale-[0.5]' : ''}`}>
      <Label className="text-xs text-muted-foreground">{label}</Label>
      {children}
    </div>
  )
}

function SwitchRow({
  label, checked, disabled = false, onChange, tooltip,
}: {
  label: string
  checked: boolean
  disabled?: boolean
  onChange: (v: boolean) => void
  tooltip?: string
}) {
  return (
    <div className={`flex items-center justify-between transition-opacity ${disabled ? 'opacity-40 grayscale-[0.6]' : ''}`}>
      <div className="flex items-center gap-1">
        <Label className="text-xs text-muted-foreground">{label}</Label>
        {tooltip && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Badge variant="outline" className="h-3.5 w-3.5 cursor-help text-[9px] p-0 flex items-center justify-center opacity-70 hover:opacity-100 transition-opacity">?</Badge>
            </TooltipTrigger>
            <TooltipContent side="left" className="max-w-56 text-xs">{tooltip}</TooltipContent>
          </Tooltip>
        )}
      </div>
      <Switch checked={checked} onCheckedChange={onChange} disabled={disabled} />
    </div>
  )
}
