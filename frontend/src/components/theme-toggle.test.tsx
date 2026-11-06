import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import { ThemeToggle } from './theme-toggle'

afterEach(() => {
  delete document.documentElement.dataset.theme
  localStorage.clear()
})

describe('mode d’affichage', () => {
  it('passe du mode sombre au mode clair et garde le choix', async () => {
    render(<ThemeToggle />)

    await userEvent.click(screen.getByRole('button', { name: 'Mode clair' }))
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(localStorage.getItem('pilot-theme')).toBe('light')

    await userEvent.click(screen.getByRole('button', { name: 'Mode sombre' }))
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('pilot-theme')).toBe('dark')
  })
})
