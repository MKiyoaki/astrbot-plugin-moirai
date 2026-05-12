'use client'

import { Card, CardContent } from '@/components/ui/card'
import { useApp } from '@/lib/store'
import {
  ChartContainer, ChartTooltip, ChartTooltipContent,
} from '@/components/ui/chart'
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from 'recharts'

interface ActivityChartProps {
  timeData: { date: string; count: number }[]
}

export function ActivityChart({ timeData }: ActivityChartProps) {
  const { i18n, lang } = useApp()

  const chartConfig = {
    count: { label: i18n.stats.events, color: 'var(--primary)' },
  }

  return (
    <Card className="border-border/50 h-full">
      <div className="px-6 pt-5 pb-3 border-b border-border/40">
        <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground font-mono">
          {i18n.stats.activity30d}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5">
          {lang === 'zh' ? '每日事件数，近30日' : 'Daily event count, last 30 days'}
        </p>
      </div>
      <CardContent className="px-2 pb-4 pt-4">
        {timeData.length === 0 ? (
          <div className="h-[220px] flex items-center justify-center text-xs text-muted-foreground/40 italic">
            {i18n.stats.noData}
          </div>
        ) : (
          <ChartContainer config={chartConfig} className="h-[220px] w-full">
            <BarChart data={timeData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} strokeDasharray="3 3" className="stroke-border/40" />
              <XAxis
                dataKey="date"
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => v.split('-').slice(1).join('/')}
                minTickGap={28}
                className="fill-muted-foreground text-[10px]"
              />
              <YAxis hide />
              <ChartTooltip cursor={false} content={<ChartTooltipContent hideLabel />} />
              <Bar dataKey="count" fill="var(--color-count)" radius={[3, 3, 0, 0]} barSize={20} />
            </BarChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  )
}
