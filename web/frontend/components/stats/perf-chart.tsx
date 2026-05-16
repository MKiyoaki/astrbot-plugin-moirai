'use client'

import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useApp } from '@/lib/store'
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RechartsTooltip,
} from 'recharts'

interface PerfEntry {
  name: string
  value: number
}

interface PerfChartProps {
  perfData: PerfEntry[]
  totalTime: number
}

const COLORS = [
  'var(--primary)',
  'var(--accent-foreground)',
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
  'var(--chart-6)',
  'var(--chart-7)',
  'var(--chart-8)',
]

export function PerfChart({ perfData, totalTime }: PerfChartProps) {
  const { i18n, lang } = useApp()

  const noData = perfData.length === 0

  return (
    <Card className="overflow-hidden border-border/50">
      <div className="px-6 pt-5 pb-3 border-b border-border/40 flex items-center justify-between">
        <div>
          <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground font-mono">
            {i18n.stats.perf}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {lang === 'zh' ? '各阶段平均耗时（秒）' : 'Average latency per phase (seconds)'}
          </p>
        </div>
        <Badge variant="secondary" className="font-mono text-[10px]">
          {lang === 'zh' ? '累计' : 'Total'} {totalTime.toFixed(3)}s
        </Badge>
      </div>

      <CardContent className="p-0">
        <div className="grid grid-cols-1 lg:grid-cols-5 min-h-[360px]">
          {/* Donut */}
          <div className="lg:col-span-3 p-6 flex items-center justify-center relative min-h-[280px]">
            {noData ? (
              <p className="text-xs text-muted-foreground/50 italic">
                {lang === 'zh' ? '运行插件以记录性能' : 'Run plugin to record performance data'}
              </p>
            ) : (
              <>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={perfData}
                      cx="50%" cy="50%"
                      innerRadius={72} outerRadius={110}
                      paddingAngle={4}
                      dataKey="value"
                      animationBegin={0}
                      animationDuration={900}
                    >
                      {perfData.map((_, i) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Pie>
                    <RechartsTooltip
                      content={({ active, payload }) => {
                        if (!active || !payload?.length) return null
                        const d = payload[0].payload
                        return (
                          <div className="bg-background/95 border border-border/60 p-2.5 rounded shadow-lg text-xs">
                            <p className="font-semibold mb-1">{d.name}</p>
                            <p className="font-mono text-accent-foreground">{d.value.toFixed(3)}s</p>
                            <p className="text-muted-foreground text-[10px] mt-0.5">
                              {((d.value / totalTime) * 100).toFixed(1)}%
                            </p>
                          </div>
                        )
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                {/* Center label */}
                <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                  <span className="text-2xl font-bold tabular-nums font-mono">
                    {perfData.reduce((max, p) => p.value > max.value ? p : max, perfData[0]).value.toFixed(2)}s
                  </span>
                  <span className="text-[9px] uppercase tracking-widest text-muted-foreground">
                    {lang === 'zh' ? '峰值' : 'Peak'}
                  </span>
                </div>
              </>
            )}
          </div>

          {/* Legend */}
          <div className="lg:col-span-2 border-l border-border/40 flex flex-col">
            <div className="px-4 py-3 border-b border-border/40 flex justify-between text-[9px] uppercase tracking-widest text-muted-foreground font-mono">
              <span>{lang === 'zh' ? '环节' : 'Phase'}</span>
              <span>{lang === 'zh' ? '耗时' : 'Time'}</span>
            </div>
            <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
              {noData ? (
                <p className="text-[10px] text-muted-foreground/40 italic pt-4 text-center">—</p>
              ) : perfData.map((p, i) => (
                <div key={p.name} className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                    <span className="text-xs truncate">{p.name}</span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <div className="w-12 h-0.5 bg-muted rounded-full overflow-hidden">
                      <div className="h-full opacity-70" style={{ width: `${(p.value / totalTime) * 100}%`, backgroundColor: COLORS[i % COLORS.length] }} />
                    </div>
                    <span className="text-[11px] font-mono font-bold w-14 text-right">{p.value.toFixed(3)}s</span>
                  </div>
                </div>
              ))}
            </div>
            <div className="px-4 py-3 border-t border-border/40">
              <p className="text-[9px] text-muted-foreground/60 leading-relaxed">
                {lang === 'zh'
                  ? '核心路径任务（响应、召回）在对话时触发；后台任务周期触发。'
                  : 'Core path tasks trigger during chat; background tasks run periodically.'}
              </p>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
