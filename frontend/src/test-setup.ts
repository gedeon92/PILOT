import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterEach } from 'vitest'

// Les pages sont chargées à la demande (lazy-pages.ts) : sur une machine de vérification plus
// lente, la première ouverture d'une page peut dépasser la seconde d'attente par défaut.
configure({ asyncUtilTimeout: 5000 })

// Sans `globals: true`, Testing Library ne vide pas le DOM entre deux tests.
afterEach(() => {
  cleanup()
})
