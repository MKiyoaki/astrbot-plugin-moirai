import { RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useApp } from '@/lib/store'
import { cn } from '@/lib/utils'

interface RefreshButtonProps {
  onClick: () => void | Promise<void>
  loading: boolean
  className?: string
  title?: string
}

export function RefreshButton({ onClick, loading, className, title }: RefreshButtonProps) {
  const { i18n } = useApp()
  
  return (
    <Button 
      variant="outline" 
      size="icon" 
      onClick={onClick} 
      title={title ?? i18n.common.refresh} 
      className={cn("h-8 w-8", className)}
    >
      <RefreshCw 
        className={cn(
          "size-3.5 transition-transform duration-500", 
          loading && "animate-spin"
        )} 
      />
    </Button>
  )
}
