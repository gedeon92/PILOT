import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'
import { ApiError } from './client'

/** Client de requêtes de l'application.
 * Session expirée (401) pendant l'utilisation : on oublie l'utilisateur, ce qui renvoie vers
 * la connexion, puis vers la page en cours une fois reconnecté. */
export function createQueryClient({ retry = true }: { retry?: boolean } = {}) {
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError: (error) => onError(error) }),
    mutationCache: new MutationCache({ onError: (error) => onError(error) }),
    defaultOptions: {
      queries: {
        // Une erreur 4xx est une réponse définitive : inutile de réessayer.
        retry: retry
          ? (count, error) =>
              !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2
          : false,
        refetchOnWindowFocus: false,
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
