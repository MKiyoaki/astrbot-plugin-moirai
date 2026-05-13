'use client'

import Link from 'next/link'
import { FileQuestion, Home, ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function NotFound() {
  return (
    <div className="flex h-full flex-col items-center justify-center p-4 text-center">
      <div className="bg-muted mb-6 flex size-24 items-center justify-center rounded-full">
        <FileQuestion className="text-muted-foreground size-12 opacity-50" />
      </div>
      
      <h1 className="mb-2 text-4xl font-bold tracking-tight">404</h1>
      <h2 className="mb-4 text-xl font-semibold">页面未找到</h2>
      
      <p className="text-muted-foreground mb-8 max-w-md">
        抱歉，我们找不到您请求的页面。它可能已被移动、删除，或者您输入的地址有误。
      </p>
      
      <div className="flex flex-wrap items-center justify-center gap-4">
        <Button variant="outline" asChild>
          <button onClick={() => window.history.back()} className="flex items-center gap-2">
            <ArrowLeft className="size-4" />
            返回上一页
          </button>
        </Button>
        
        <Button asChild>
          <Link href="/" className="flex items-center gap-2">
            <Home className="size-4" />
            回到首页
          </Link>
        </Button>
      </div>
    </div>
  )
}
