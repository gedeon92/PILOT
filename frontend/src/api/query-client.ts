import { toast } from '../toast'
import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'
import { ApiError } from './client'

/** Client de requêtes de l'application.
 * Session expirée (401) pendant l'utilisation : on oublie l'utilisateur, ce qui renvoie vers
 * la connexion, puis vers la page en cours une fois reconnecté. */
export function createQueryClient({ retry = true }: { retry?: boolean } = {}) {
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError: (error) => onError(error) }),
    mutationCache: new MutationCache({
      onError: (error) => onError(error),
      // Confirmation animée déclarée par l'action : texte fixe, ou calculé d'après les données.
      onSuccess: (data, variables, _context, mutation) => {
        const success = mutation.meta?.success
        const text = typeof success === 'function' ? success(variables, data) : success
        if (typeof text === 'string' && text) toast(text)
      },
    }),
    defaultOptions: {
      queries: {
        // Une erreur 4xx est une réponse définitive : inutile de réessayer.
        retry: retry
          ? (count, error) =>
              !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2
          : false,
        refetchOnWindowFocus: false,
        // Application vivante : les données se rafraîchissent seules toutes les 30 s tant que
        // l'onglet est ouvert et visible (ce qu'un collègue modifie apparaît sans recharger).
        refetchInterval: 30_000,
        refetchIntervalInBackground: false,
      },
    },
  })
  function onError(error: unknown) {
    if (error instanceof ApiError && error.status === 401 && client.getQueryData(['me'])) {
      client.setQueryData(['me'], null)
    }
  }
  return client
}

declare module '@tanstack/react-query' {
  interface Register {
    mutationMeta: {
      /** Message de confirmation affiché après la réussite de l'action. */
      success?: string | ((variables: unknown, data: unknown) => string | null)
    }
  }
}
