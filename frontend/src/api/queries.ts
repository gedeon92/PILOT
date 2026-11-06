import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  api,
  type AlertList,
  type AlertPreferences,
  ApiError,
  type DocumentItem,
  type HistoryEntry,
  type ImportResult,
  type InvitationInfo,
  type InvitationLink,
  type Me,
  type Member,
  type Project,
  type ProjectLink,
  type Proposal,
  type Role,
  type Space,
  type SpaceSummary,
  type Task,
  type UpdateRequest,
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

export function useForgotPassword() {
  return useMutation({
    mutationFn: (email: string) =>
      api<{ message: string }>('/auth/password-reset', { method: 'POST', body: { email } }),
  })
}

export function useResetPassword() {
  const setMe = useSetMe()
  return useMutation({
    mutationFn: (body: { token: string; new_password: string }) =>
      api<Me>('/auth/password-reset/confirm', { method: 'POST', body }),
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

export type CatalogResource = 'portfolios' | 'entities' | 'project-types' | 'programs'

/** Forme commune des portefeuilles, filiales et types de projets. */
export type CatalogItem = {
  id: string
  name: string
  archived: boolean
  version: number
  description?: string | null
  color?: string
  emoji?: string | null
  country?: string | null
  kind?: string
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

// ---------- Projets et tâches ----------

const projectKeys = {
  all: (spaceId: string) => ['space', spaceId, 'projects'] as const,
  one: (spaceId: string, projectId: string) => ['space', spaceId, 'projects', projectId] as const,
}

export type ProjectFilters = {
  portfolio_id?: string
  status?: string
  q?: string
  kind?: string
  program_id?: string
}

/** Complète les champs récents qu'un serveur pas encore mis à jour ne renvoie pas
 * (pendant un déploiement, l'interface peut arriver quelques minutes avant l'API). */
function withDefaults(project: Project): Project {
  return {
    ...project,
    contributors: project.contributors ?? [],
    decision_options: project.decision_options ?? [],
  }
}

export function useProjects(spaceId: string, filters: ProjectFilters = {}) {
  const params = new URLSearchParams(
    Object.entries(filters).filter((entry): entry is [string, string] => Boolean(entry[1])),
  ).toString()
  return useQuery({
    queryKey: [...projectKeys.all(spaceId), 'list', params],
    queryFn: async () =>
      (await api<Project[]>(`/spaces/${spaceId}/projects${params ? `?${params}` : ''}`)).map(
        withDefaults,
      ),
  })
}

export function useProject(spaceId: string, projectId: string) {
  return useQuery({
    queryKey: [...projectKeys.one(spaceId, projectId), 'detail'],
    queryFn: async () =>
      withDefaults(await api<Project>(`/spaces/${spaceId}/projects/${projectId}`)),
  })
}

export function useTasks(spaceId: string, projectId: string) {
  return useQuery({
    queryKey: [...projectKeys.one(spaceId, projectId), 'tasks'],
    queryFn: () => api<Task[]>(`/spaces/${spaceId}/projects/${projectId}/tasks`),
  })
}

export function useHistory(spaceId: string, projectId: string) {
  return useQuery({
    queryKey: [...projectKeys.one(spaceId, projectId), 'history'],
    queryFn: () => api<HistoryEntry[]>(`/spaces/${spaceId}/projects/${projectId}/history`),
  })
}

/** Toute écriture sur un projet rafraîchit la liste, la fiche, les tâches et l'historique. */
function useRefreshProjects(spaceId: string) {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: projectKeys.all(spaceId) })
}

export function useCreateProject(spaceId: string) {
  const refresh = useRefreshProjects(spaceId)
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api<Project>(`/spaces/${spaceId}/projects`, { method: 'POST', body }),
    onSuccess: refresh,
  })
}

export function useUpdateProject(spaceId: string, projectId: string) {
  const refresh = useRefreshProjects(spaceId)
  return useMutation({
    mutationFn: (body: Record<string, unknown> & { version: number }) =>
      api<Project>(`/spaces/${spaceId}/projects/${projectId}`, { method: 'PATCH', body }),
    onSuccess: refresh,
  })
}

export function useChangeProjectStatus(spaceId: string, projectId: string) {
  const refresh = useRefreshProjects(spaceId)
  return useMutation({
    mutationFn: (body: { version: number; status: string; outcome?: string; reason?: string }) =>
      api<Project>(`/spaces/${spaceId}/projects/${projectId}/status`, { method: 'POST', body }),
    onSuccess: refresh,
  })
}

export function useCreateTask(spaceId: string, projectId: string) {
  const refresh = useRefreshProjects(spaceId)
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api<Task>(`/spaces/${spaceId}/projects/${projectId}/tasks`, { method: 'POST', body }),
    onSuccess: refresh,
  })
}

/** Tâche créée depuis la page Tâches : dans un projet, ou sans projet (suivi général). */
export function useCreateSpaceTask(spaceId: string) {
  const refresh = useRefreshProjects(spaceId)
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api<Task>(`/spaces/${spaceId}/tasks`, { method: 'POST', body }),
    onSuccess: refresh,
  })
}

export function useUpdateTask(spaceId: string) {
  const refresh = useRefreshProjects(spaceId)
  return useMutation({
    mutationFn: ({ task, changes }: { task: Task; changes: Record<string, unknown> }) =>
      api<Task>(`/spaces/${spaceId}/tasks/${task.id}`, {
        method: 'PATCH',
        body: { ...changes, version: task.version },
      }),
    onSettled: refresh,
  })
}

// ---------- Liens entre projets ----------

export function useProjectLinks(spaceId: string, projectId: string) {
  return useQuery({
    queryKey: [...projectKeys.one(spaceId, projectId), 'links'],
    queryFn: () => api<ProjectLink[]>(`/spaces/${spaceId}/projects/${projectId}/links`),
  })
}

export function useAddProjectLink(spaceId: string, projectId: string) {
  const refresh = useRefreshProjects(spaceId)
  return useMutation({
    mutationFn: (body: { project_id: string; note: string | null }) =>
      api<ProjectLink>(`/spaces/${spaceId}/projects/${projectId}/links`, { method: 'POST', body }),
    onSettled: refresh,
  })
}

export function useRemoveProjectLink(spaceId: string, projectId: string) {
  const refresh = useRefreshProjects(spaceId)
  return useMutation({
    mutationFn: (otherId: string) =>
      api<void>(`/spaces/${spaceId}/projects/${projectId}/links/${otherId}`, {
        method: 'DELETE',
      }),
    onSettled: refresh,
  })
}

// ---------- Documents ----------

export function useProjectDocuments(spaceId: string, projectId: string) {
  return useQuery({
    queryKey: [...projectKeys.one(spaceId, projectId), 'documents'],
    queryFn: () => api<DocumentItem[]>(`/spaces/${spaceId}/projects/${projectId}/documents`),
  })
}

/** Une page de plus que demandé est chargée pour savoir s'il en reste. */
export function useSpaceDocuments(spaceId: string, q: string, limit = 50) {
  return useQuery({
    queryKey: [...projectKeys.all(spaceId), 'documents', q, limit],
    queryFn: async () => {
      const params = new URLSearchParams({ limit: String(limit + 1) })
      if (q) params.set('q', q)
      const rows = await api<DocumentItem[]>(`/spaces/${spaceId}/documents?${params}`)
      return { items: rows.slice(0, limit), more: rows.length > limit }
    },
    placeholderData: (previous) => previous,
  })
}

export function useUploadDocument(spaceId: string, projectId: string) {
  const refresh = useRefreshProjects(spaceId)
  return useMutation({
    mutationFn: (file: File) => {
      const body = new FormData()
      body.append('file', file)
      return api<DocumentItem>(`/spaces/${spaceId}/projects/${projectId}/documents`, {
        method: 'POST',
        body,
      })
    },
    onSettled: refresh,
  })
}

export function useReplaceDocument(spaceId: string) {
  const refresh = useRefreshProjects(spaceId)
  return useMutation({
    mutationFn: ({ documentId, file }: { documentId: string; file: File }) => {
      const body = new FormData()
      body.append('file', file)
      return api<DocumentItem>(`/spaces/${spaceId}/documents/${documentId}/replace`, {
        method: 'POST',
        body,
      })
    },
    onSettled: refresh,
  })
}

export function useDocumentVersions(spaceId: string, documentId: string, enabled: boolean) {
  return useQuery({
    queryKey: [...projectKeys.all(spaceId), 'document-versions', documentId],
    queryFn: () => api<DocumentItem[]>(`/spaces/${spaceId}/documents/${documentId}/versions`),
    enabled,
  })
}

export function useArchiveDocument(spaceId: string) {
  const refresh = useRefreshProjects(spaceId)
  return useMutation({
    mutationFn: (documentId: string) =>
      api<DocumentItem>(`/spaces/${spaceId}/documents/${documentId}/archive`, { method: 'POST' }),
    onSettled: refresh,
  })
}

export function downloadUrl(spaceId: string, documentId: string) {
  return `/api/spaces/${spaceId}/documents/${documentId}/download`
}

/** Tâches ouvertes de tout l'espace (jalons de la timeline). */
export function useSpaceTasks(spaceId: string, includeClosed = false) {
  return useQuery({
    queryKey: [...projectKeys.all(spaceId), includeClosed ? 'all-tasks' : 'open-tasks'],
    queryFn: () =>
      api<Task[]>(`/spaces/${spaceId}/tasks${includeClosed ? '?include_closed=true' : ''}`),
  })
}

// ---------- Alertes ----------

const alertKeys = {
  list: (spaceId: string) => ['space', spaceId, 'alerts'] as const,
  prefs: (spaceId: string) => ['space', spaceId, 'alert-preferences'] as const,
}

export function useAlerts(spaceId: string) {
  return useQuery({
    queryKey: alertKeys.list(spaceId),
    queryFn: () => api<AlertList>(`/spaces/${spaceId}/alerts`),
    // Le compteur du menu se met à jour régulièrement.
    refetchInterval: 5 * 60_000,
  })
}

function useRefreshAlerts(spaceId: string) {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: alertKeys.list(spaceId) })
}

export function useMarkAlertRead(spaceId: string) {
  const refresh = useRefreshAlerts(spaceId)
  return useMutation({
    mutationFn: (alertId: string) =>
      api(`/spaces/${spaceId}/alerts/${alertId}/read`, { method: 'POST' }),
    onSettled: refresh,
  })
}

export function useMarkAllAlertsRead(spaceId: string) {
  const refresh = useRefreshAlerts(spaceId)
  return useMutation({
    mutationFn: () => api<void>(`/spaces/${spaceId}/alerts/read-all`, { method: 'POST' }),
    onSettled: refresh,
  })
}

export function useAlertPreferences(spaceId: string) {
  return useQuery({
    queryKey: alertKeys.prefs(spaceId),
    queryFn: () => api<AlertPreferences>(`/spaces/${spaceId}/alert-preferences`),
  })
}

export function useSaveAlertPreferences(spaceId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { disabled_rules: string[]; email_digest: boolean; digest_hour: number }) =>
      api<AlertPreferences>(`/spaces/${spaceId}/alert-preferences`, { method: 'PUT', body }),
    onSuccess: (data) => {
      queryClient.setQueryData(alertKeys.prefs(spaceId), data)
      queryClient.invalidateQueries({ queryKey: alertKeys.list(spaceId) })
    },
  })
}

export function useSendTestEmail(spaceId: string) {
  return useMutation({
    mutationFn: () =>
      api<{ sent: boolean; message: string }>(`/spaces/${spaceId}/alert-preferences/test-email`, {
        method: 'POST',
      }),
  })
}

// ---------- Mon compte ----------

export function useUpdateProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { display_name: string }) => api<Me>('/auth/me', { method: 'PATCH', body }),
    onSuccess: (me) => queryClient.setQueryData(keys.me, me),
  })
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) =>
      api<void>('/auth/password', { method: 'POST', body }),
  })
}

export function useRequestEmailChange() {
  return useMutation({
    mutationFn: (body: { new_email: string; password: string }) =>
      api<{ sent_to: string; expires_hours: number }>('/auth/email-change', {
        method: 'POST',
        body,
      }),
  })
}

export function useConfirmEmailChange() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (token: string) =>
      api<Me>('/auth/email-change/confirm', { method: 'POST', body: { token } }),
    onSuccess: (me) => {
      queryClient.setQueryData(keys.me, me)
      queryClient.invalidateQueries({ queryKey: ['space'] })
    },
  })
}

// ---------- Boîte de mise à jour ----------

const updateKeys = {
  list: (spaceId: string) => ['space', spaceId, 'updates'] as const,
}

export function useUpdates(spaceId: string, enabled = true) {
  return useQuery({
    queryKey: updateKeys.list(spaceId),
    queryFn: () => api<UpdateRequest[]>(`/spaces/${spaceId}/updates`),
    enabled,
  })
}

/** Après une décision : la liste, les projets et les alertes changent. */
function useRefreshAfterDecision(spaceId: string) {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: updateKeys.list(spaceId) }),
      queryClient.invalidateQueries({ queryKey: projectKeys.all(spaceId) }),
      queryClient.invalidateQueries({ queryKey: alertKeys.list(spaceId) }),
    ])
}

export type UpdateDraft = {
  message: string
  files: File[]
  visibility: 'private' | 'shared'
  clientRequestId: string
}

export function useSendUpdate(spaceId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (draft: UpdateDraft) => {
      const body = new FormData()
      body.append('message', draft.message)
      body.append('visibility', draft.visibility)
      body.append('client_request_id', draft.clientRequestId)
      for (const file of draft.files) body.append('files', file)
      return api<UpdateRequest>(`/spaces/${spaceId}/updates`, { method: 'POST', body })
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: updateKeys.list(spaceId) }),
  })
}

export function useSetUpdateVisibility(spaceId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, visibility }: { id: string; visibility: 'private' | 'shared' }) =>
      api<UpdateRequest>(`/spaces/${spaceId}/updates/${id}`, {
        method: 'PATCH',
        body: { visibility },
      }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: updateKeys.list(spaceId) }),
  })
}

export function useApplyProposal(spaceId: string) {
  const refresh = useRefreshAfterDecision(spaceId)
  return useMutation({
    mutationFn: ({
      id,
      fields,
      baseVersion,
    }: {
      id: string
      fields: string[]
      baseVersion: number
    }) =>
      api<Proposal>(`/spaces/${spaceId}/proposals/${id}/apply`, {
        method: 'POST',
        body: { fields, base_version: baseVersion },
      }),
    onSettled: refresh,
  })
}

export function useDiscardProposal(spaceId: string) {
  const refresh = useRefreshAfterDecision(spaceId)
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      api<Proposal>(`/spaces/${spaceId}/proposals/${id}/discard`, {
        method: 'POST',
        body: { reason: reason || null },
      }),
    onSettled: refresh,
  })
}

export function useChooseProposalTarget(spaceId: string) {
  const refresh = useRefreshAfterDecision(spaceId)
  return useMutation({
    mutationFn: ({ id, projectId }: { id: string; projectId: string }) =>
      api<Proposal>(`/spaces/${spaceId}/proposals/${id}/target`, {
        method: 'POST',
        body: { project_id: projectId },
      }),
    onSettled: refresh,
  })
}

export function useRefreshProposal(spaceId: string) {
  const refresh = useRefreshAfterDecision(spaceId)
  return useMutation({
    mutationFn: (id: string) =>
      api<Proposal>(`/spaces/${spaceId}/proposals/${id}/refresh`, { method: 'POST' }),
    onSettled: refresh,
  })
}

export function useShareSource(spaceId: string) {
  const refresh = useRefreshAfterDecision(spaceId)
  return useMutation({
    mutationFn: ({ sourceId, projectId }: { sourceId: string; projectId: string }) =>
      api<DocumentItem>(`/spaces/${spaceId}/update-sources/${sourceId}/share`, {
        method: 'POST',
        body: { project_id: projectId },
      }),
    onSettled: refresh,
  })
}

export function sourceDownloadUrl(spaceId: string, sourceId: string) {
  return `/api/spaces/${spaceId}/update-sources/${sourceId}/download`
}

// ---------- Export et import ----------

export function exportUrl(spaceId: string, withFiles: boolean) {
  return `/api/spaces/${spaceId}/export${withFiles ? '' : '?files=false'}`
}

export function useImportSpace() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => {
      const body = new FormData()
      body.append('file', file)
      return api<ImportResult>('/space-imports', { method: 'POST', body })
    },
    // Le nouvel espace apparaît dans le sélecteur d'espaces.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.me }),
  })
}
