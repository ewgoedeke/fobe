import * as React from 'react'
import * as TogglePrimitive from '@radix-ui/react-toggle'
import { cn } from '@/lib/utils'

function Toggle({ className, variant = 'default', size = 'default', ...props }) {
  return (
    <TogglePrimitive.Root
      data-slot="toggle"
      className={cn(
        'inline-flex items-center justify-center gap-1.5 rounded-md text-sm font-medium transition-colors hover:bg-muted hover:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 data-[state=on]:bg-accent data-[state=on]:text-accent-foreground cursor-pointer',
        variant === 'outline' &&
          'border border-input bg-transparent shadow-xs hover:bg-accent hover:text-accent-foreground',
        size === 'default' && 'h-9 px-3',
        size === 'sm' && 'h-7 px-2 text-xs',
        size === 'lg' && 'h-10 px-4',
        className
      )}
      {...props}
    />
  )
}

export { Toggle }
