import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ExportDropdown } from '@/components/ExportDropdown'

describe('ExportDropdown', () => {
  it('renders the export button', () => {
    render(
      <ExportDropdown onExportCSV={vi.fn()} onExportJSON={vi.fn()} />
    )

    expect(screen.getByText('Экспорт')).toBeInTheDocument()
  })

  it('shows dropdown items when clicked', async () => {
    const user = userEvent.setup()

    render(
      <ExportDropdown onExportCSV={vi.fn()} onExportJSON={vi.fn()} />
    )

    await user.click(screen.getByText('Экспорт'))

    expect(screen.getByText('Экспорт CSV')).toBeInTheDocument()
    expect(screen.getByText('Экспорт JSON')).toBeInTheDocument()
  })

  it('calls onExportCSV when CSV option is selected', async () => {
    const user = userEvent.setup()
    const onExportCSV = vi.fn()

    render(
      <ExportDropdown onExportCSV={onExportCSV} onExportJSON={vi.fn()} />
    )

    await user.click(screen.getByText('Экспорт'))
    await user.click(screen.getByText('Экспорт CSV'))

    expect(onExportCSV).toHaveBeenCalledOnce()
  })

  it('calls onExportJSON when JSON option is selected', async () => {
    const user = userEvent.setup()
    const onExportJSON = vi.fn()

    render(
      <ExportDropdown onExportCSV={vi.fn()} onExportJSON={onExportJSON} />
    )

    await user.click(screen.getByText('Экспорт'))
    await user.click(screen.getByText('Экспорт JSON'))

    expect(onExportJSON).toHaveBeenCalledOnce()
  })

  it('disables the button when disabled prop is true', () => {
    render(
      <ExportDropdown
        onExportCSV={vi.fn()}
        onExportJSON={vi.fn()}
        disabled={true}
      />
    )

    const button = screen.getByRole('button')
    expect(button).toBeDisabled()
  })
})
