'use client'

import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Pagination, PaginationContent, PaginationItem,
  PaginationNext, PaginationPrevious,
} from '@/components/ui/pagination'
import { useApp } from '@/lib/store'

interface PaginationFooterProps {
  totalItems: number
  totalPages: number
  pageSize: number
  currentPage: number
  onPageChange: (p: number) => void
  onPageSizeChange: (sz: number) => void
}

export function PaginationFooter({
  totalItems, totalPages, pageSize, currentPage, onPageChange, onPageSizeChange,
}: PaginationFooterProps) {
  const { i18n } = useApp()
  const pt = i18n.common.pagination

  return (
    <div className="flex items-center justify-between border-t border-border/50 px-2 py-3 mt-2 shrink-0">
      <div className="flex items-center gap-2 text-xs text-muted-foreground font-mono">
        <span className="uppercase tracking-wider text-[9px]">{pt.pageSize}</span>
        <Select value={pageSize.toString()} onValueChange={(v) => onPageSizeChange(Number(v))}>
          <SelectTrigger className="h-7 w-[60px] text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {[25, 50, 100].map(n => (
              <SelectItem key={n} value={String(n)}>{n}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex items-center gap-4">
        <span className="text-[10px] font-mono text-muted-foreground">
          {pt.totalItems.replace('{count}', String(totalItems))} ·{' '}
          {pt.pageInfo.replace('{current}', String(currentPage)).replace('{total}', String(totalPages))}
        </span>
        <Pagination className="justify-end w-auto mx-0">
          <PaginationContent>
            <PaginationItem>
              <PaginationPrevious
                href="#"
                size="sm"
                label={pt.previous}
                onClick={(e) => { e.preventDefault(); if (currentPage > 1) onPageChange(currentPage - 1) }}
                className={currentPage === 1 ? 'pointer-events-none opacity-40' : 'cursor-pointer'}
              />
            </PaginationItem>
            <PaginationItem>
              <PaginationNext
                href="#"
                size="sm"
                label={pt.next}
                onClick={(e) => { e.preventDefault(); if (currentPage < totalPages) onPageChange(currentPage + 1) }}
                className={currentPage === totalPages ? 'pointer-events-none opacity-40' : 'cursor-pointer'}
              />
            </PaginationItem>
          </PaginationContent>
        </Pagination>
      </div>
    </div>
  )
}
