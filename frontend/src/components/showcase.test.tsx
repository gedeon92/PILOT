import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Showcase } from './showcase'

describe('présentation animée de PILOT', () => {
  it('explique l’application et décrit le dessin animé', () => {
    render(<Showcase />)

    expect(screen.getByRole('heading', { name: /Vos projets avancent/ })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Illustration animée/ })).toBeInTheDocument()
    expect(screen.getByText('Ajoutez vos projets')).toBeInTheDocument()
    expect(screen.getByText('Suivez leur avancement')).toBeInTheDocument()
    expect(screen.getByText('Préparez vos événements')).toBeInTheDocument()
  })
})
