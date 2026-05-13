import type { Metadata } from 'next'
import { Geist, Geist_Mono, PT_Serif_Caption } from 'next/font/google'
import './globals.css'
import { ThemeProvider } from '@/components/theme-provider'
import { AppProvider } from '@/lib/store'
import { cn } from '@/lib/utils'
import { AppShell } from '@/components/layout/app-shell'

const geist = Geist({ subsets: ['latin'], variable: '--font-sans' })
const geistMono = Geist_Mono({ subsets: ['latin'], variable: '--font-mono' })
const ptSerif = PT_Serif_Caption({ weight: '400', subsets: ['latin'], variable: '--font-serif' })

export const metadata: Metadata = {
  title: 'Moirai',
  description: '三轴长期记忆面板',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning className={cn('theme-moirai', geist.variable, geistMono.variable, ptSerif.variable)}>
      <body className="font-sans antialiased min-h-svh">
        <ThemeProvider>
          <AppProvider>
            <AppShell>{children}</AppShell>
          </AppProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
