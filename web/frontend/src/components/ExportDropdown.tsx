import { Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

interface ExportDropdownProps {
  onExportCSV: () => void
  onExportJSON: () => void
  disabled?: boolean
}

export function ExportDropdown({ onExportCSV, onExportJSON, disabled }: ExportDropdownProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" disabled={disabled} className="gap-1.5">
          <Download className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Экспорт</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={onExportCSV}>
          Экспорт CSV
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={onExportJSON}>
          Экспорт JSON
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
