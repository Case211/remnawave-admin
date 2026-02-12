import { Download } from 'lucide-react'
import { useTranslation } from 'react-i18next'
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
  const { t } = useTranslation()
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" disabled={disabled} className="gap-1.5">
          <Download className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">{t('common.export.export')}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={onExportCSV}>
          {t('common.export.csv')}
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={onExportJSON}>
          {t('common.export.json')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
