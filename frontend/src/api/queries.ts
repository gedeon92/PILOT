import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  api,
  ApiError,
  type InvitationInfo,
  type InvitationLink,
  type Me,
  type Member,
  type Role,
  type Space,
  type SpaceSummary,
} from './client'

export const keys = {
  me: ['me'] as const,
  space: (id: string) => ['space', id] as const,
  members: (id: string) => ['space', id, 'members'] as const,
}

/** `null` quand personne n'est connecté. */
export function useMe() {
  return useQuery({
    queryKey: keys.me,
    queryFn: async () => {
      try {
        return await api<Me>('/auth/me')
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null
        throw error
      }
    },
  })
}

function useSetMe() {
  const queryClient = useQueryClient()
  return (me: Me | null) => {
    queryClient.setQueryData(keys.me, me)
  }
}

export function useLogin() {
  const setMe = useSetMe()
  return useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      api<Me>('/auth/login', { method: 'POST', body }),
    onSuccess: setMe,
  })
}

export function useRegister() {
  const setMe = useSetMe()
  return useMutation({
    mutationFn: (body: { email: string; password: string; display_name: string }) =>
      api<Me>('/auth/register', { method: 'POST', body }),
    onSuccess: setMe,
  })
}

export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api<void>('/auth/logout', { method: 'POST' }),
    onSuccess: () => {
      queryClient.clear()
      queryClient.setQueryData(keys.me, null)
    },
  })
}

export function useCreateSpace() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; timezone: string }) =>
      api<Space>('/spaces', { method: 'POST', body }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.me }),
  })
}

export function useSpace(spaceId: string) {
  return useQuery({
    queryKey: keys.space(spaceId),
    queryFn: () => api<Space>(`/spaces/${spaceId}`),
  })
}

export function useMembers(spaceId: string) {
  return useQuery({
    queryKey: keys.members(spaceId),
    queryFn: () => api<Member[]>(`/spaces/${spaceId}/members`),
  })
}

function useRefreshMembers(spaceId: string) {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: keys.members(spaceId) })
}

export function useInvite(spaceId: string) {
  const refresh = useRefreshMembers(spaceId)
  return useMutation({
    mutationFn: (body: { email: string; role: Exclude<Role, 'owner'> }) =>
      api<InvitationLink>(`/spaces/${spaceId}/invitations`, { method: 'POST', body }),
    onSuccess: refresh,
  })
}

export function useRenewInvitation(spaceId: string) {
  const refresh = useRefreshMembers(spaceId)
  return useMutation({
    mutationFn: (memberId: string) =>
      api<InvitationLink>(`/spaces/${spaceId}/members/${memberId}/invitation-link`, {
        method: 'POST',
      }),
    onSuccess: refresh,
  })
}

export function useChangeRole(spaceId: string) {
  const refresh = useRefreshMembers(spaceId)
  return useMutation({
    mutationFn: ({ member, role }: { member: Member; role: Exclude<Role, 'owner'> }) =>
      api<Member>(`/spaces/${spaceId}/members/${member.id}`, {
        method: 'PATCH',
        body: { role, version: member.version },
      }),
    // En cas de conflit aussi : la liste rechargée montre la version actuelle.
    onSettled: refresh,
  })
}

export function useRemoveMember(spaceId: string) {
  const refresh = useRefreshMembers(spaceId)
  return useMutation({
    mutationFn: (memberId: string) =>
      api<void>(`/spaces/${spaceId}/members/${memberId}`, { method: 'DELETE' }),
    onSettled: refresh,
  })
}

export function useInvitationInfo(token: string, enabled: boolean) {
  return useQuery({
    queryKey: ['invitation', token],
    queryFn: () => api<InvitationInfo>('/invitations/lookup', { method: 'POST', body: { token } }),
    enabled,
  })
}

export function useAcceptInvitation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (token: string) =>
      api<SpaceSummary>('/invitations/accept', { method: 'POST', body: { token } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.me }),
  })
}

// ---------- Structure de l'espace ----------

export type CatalogResource = 'portfolios' | 'entities' | 'project-types'

/** Forme commune des portefeuilles, filiales et types de projets. */
export type CatalogItem = {
  id: string
  name: string
  archived: boolean
  version: number
  description?: string | null
  color?: string
  country?: string | null
}

export function useCatalog(spaceId: string, resource: CatalogResource, includeArchived = false) {
  return useQuery({
    queryKey: ['space', spaceId, resource, includeArchived],
    queryFn: () =>
      api<CatalogItem[]>(
        `/spaces/${spaceId}/${resource}${includeArchived ? '?include_archived=true' : ''}`,
      ),
  })
}

function useRefreshCatalog(spaceId: string, resource: CatalogResource) {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: ['space', spaceId, resource] })
}

export function useCreateCatalogItem(spaceId: string, resource: CatalogResource) {
  const refresh = useRefreshCatalog(spaceId, resource)
  return useMutation({
    mutationFn: (body: Record<string, string | null>) =>
      api<CatalogItem>(`/spaces/${spaceId}/${resource}`, { method: 'POST', body }),
    onSuccess: refresh,
  })
}

export function useUpdateCatalogItem(spaceId: string, resource: CatalogResource) {
  const refresh = useRefreshCatalog(spaceId, resource)
  return useMutation({
    mutationFn: ({ item, changes }: { item: CatalogItem; changes: Record<string, unknown> }) =>
      api<CatalogItem>(`/spaces/${spaceId}/${resource}/${item.id}`, {
        method: 'PATCH',
        body: { ...changes, version: item.version },
      }),
    onSettled: refresh,
  })
}

export function useUpdateSpace(spaceId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; timezone: string; version: number }) =>
      api<Space>(`/spaces/${spaceId}`, { method: 'PATCH', body }),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: keys.space(spaceId) })
      queryClient.invalidateQueries({ queryKey: keys.me })
    },
  })
}
