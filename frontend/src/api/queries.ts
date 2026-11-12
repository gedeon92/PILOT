import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  api,
  type AiAction,
  type AiConversation,
  type AiConversationSummary,
  type AiStatus,
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
  type ProjectAccess,
  type ProjectLink,
  type ProjectTemplate,
  type Proposal,
  type Decision,
  type Meeting,
  type Milestone,
  type Section,
  type CustomField,
  type ProjectFields,
  type TypePreview,
  type Routine,
  type RoutineProfile,
  type Occurrence,
  type Agenda,
  type Indicators,
  type Capacity,
  type EventControl,
  type Relation,
  type Encounter,
  type Role,
  type Space,
  type SpaceSummary,
  type Task,
  type TaskDetail,
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

/** Mode complet de l'espace (décision du 10 nov. 2026) : jalons, décisions, sections,
 * statuts avancés, priorité et reports motivés. Faux = mode simple (par défaut). */
export function useAdvanced(spaceId: string) {
  return Boolean(useSpace(spaceId).data?.advanced_mode)
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
    meta: { success: 'Invitation créée' },
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
    meta: { success: 'Rôle modifié' },
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
    meta: { success: 'Membre retiré' },
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
    meta: { success: 'Ajouté' },
    mutationFn: (body: Record<string, string | null>) =>
      api<CatalogItem>(`/spaces/${spaceId}/${resource}`, { method: 'POST', body }),
    onSuccess: refresh,
  })
}

export function useUpdateCatalogItem(spaceId: string, resource: CatalogResource) {
  const refresh = useRefreshCatalog(spaceId, resource)
  return useMutation({
    meta: { success: 'Modification enregistrée' },
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
    meta: { success: 'Espace enregistré' },
    mutationFn: (body: {
      name?: string
      timezone?: string
      advanced_mode?: boolean
      version: number
    }) => api<Space>(`/spaces/${spaceId}`, { method: 'PATCH', body }),
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
  // Les alertes aussi : terminer une tâche en retard doit mettre le compteur à jour tout de suite.
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: projectKeys.all(spaceId) }),
      queryClient.invalidateQueries({ queryKey: ['space', spaceId, 'alerts'] }),
    ])
}

export function useCreateProject(spaceId: string) {
  const refresh = useRefreshProjects(spaceId)
  return useMutation({
    meta: { success: 'Projet créé' },
    mutationFn: (body: Record<string, unknown>) =>
      api<Project>(`/spaces/${spaceId}/projects`, { method: 'POST', body }),
    onSuccess: refresh,
  })
}

export function useUpdateProject(spaceId: string, projectId: string) {
  const refresh = useRefreshProjects(spaceId)
  return useMutation({
    meta: { success: 'Fiche enregistrée' },
    mutationFn: (body: Record<string, unknown> & { version: number }) =>
      api<Project>(`/spaces/${spaceId}/projects/${projectId}`, { method: 'PATCH', body }),
    onSuccess: refresh,
  })
}

export function useChangeProjectStatus(spaceId: string, projectId: string) {
  const refresh = useRefreshProjects(spaceId)
  return useMutation({
    meta: { success: 'Statut du projet mis à jour' },
    mutationFn: (body: { version: number; status: string; outcome?: string; reason?: string }) =>
      api<Project>(`/spaces/${spaceId}/projects/${projectId}/status`, { method: 'POST', body }),
    onSuccess: refresh,
  })
}

export function useCreateTask(spaceId: string, projectId: string) {
  const refresh = useRefreshProjects(spaceId)
  return useMutation({
    meta: { success: 'Tâche ajoutée' },
    mutationFn: (body: Record<string, unknown>) =>
      api<Task>(`/spaces/${spaceId}/projects/${projectId}/tasks`, { method: 'POST', body }),
    onSuccess: refresh,
  })
}

export function useUpdateTask(spaceId: string) {
  const refresh = useRefreshProjects(spaceId)
  const queryClient = useQueryClient()
  return useMutation({
    meta: {
      success: (variables) => {
        const { task, changes } = variables as { task: Task; changes: { status?: string } }
        const status = changes.status
        if (status === 'done' && task.recurrence && !task.next_task_id) {
          return 'Tâche terminée : la suivante est créée'
        }
        if (status === 'done') return 'Tâche terminée'
        if (status === 'in_progress') return 'Tâche passée en cours'
        if (status === 'todo') return 'Tâche à faire'
        if (status === 'cancelled') return 'Tâche annulée'
        if (status === 'blocked') return 'Tâche bloquée'
        if (status === 'to_qualify') return 'Tâche à qualifier'
        if (status === 'awaiting_validation') return 'Tâche envoyée en validation'
        return 'Tâche enregistrée'
      },
    },
    mutationFn: ({ task, changes }: { task: Task; changes: Record<string, unknown> }) =>
      api<Task>(`/spaces/${spaceId}/tasks/${task.id}`, {
        method: 'PATCH',
        body: { ...changes, version: task.version },
      }),
    // Réaction immédiate : la case se coche (ou le statut change) tout de suite à l'écran ;
    // la liste rechargée ensuite confirme, ou corrige en cas d'échec.
    onMutate: async ({ task, changes }) => {
      const shown: Partial<Task> = {}
      for (const key of ['status', 'title', 'due_date', 'deliverable'] as const) {
        if (key in changes) (shown as Record<string, unknown>)[key] = changes[key]
      }
      if (Object.keys(shown).length === 0) return
      await queryClient.cancelQueries({ queryKey: projectKeys.all(spaceId) })
      const patch = (t: Task) => (t.id === task.id ? { ...t, ...shown } : t)
      queryClient.setQueriesData({ queryKey: projectKeys.all(spaceId) }, (old: unknown) => {
        if (Array.isArray(old)) return old.map((item) => (isTask(item) ? patch(item) : item))
        if (isTaskDetail(old)) {
          return { ...old, task: patch(old.task), subtasks: old.subtasks.map(patch) }
        }
        return old
      })
    },
    onSettled: refresh,
  })
}

function isTask(value: unknown): value is Task {
  return typeof value === 'object' && value !== null && 'assignee' in value && 'status' in value
}

function isTaskDetail(value: unknown): value is TaskDetail {
  return typeof value === 'object' && value !== null && 'task' in value && 'subtasks' in value
}

// ---------- Fiche d'une tâche : sous-tâches, commentaires, abonnés, dépendances ----------

export function useTaskDetail(spaceId: string, taskId: string | null) {
  return useQuery({
    queryKey: [...projectKeys.all(spaceId), 'task', taskId],
    queryFn: () => api<TaskDetail>(`/spaces/${spaceId}/tasks/${taskId}`),
    enabled: Boolean(taskId),
  })
}

/** Action sur une tâche (commentaire, abonnement, dépendance…) : tout est rafraîchi ensuite. */
function useTaskAction<V>(
  spaceId: string,
  request: (variables: V) => { path: string; method: 'POST' | 'DELETE'; body?: unknown },
  success?: string | ((variables: V) => string),
) {
  const refresh = useRefreshProjects(spaceId)
  return useMutation({
    meta: {
      success: success
        ? typeof success === 'function'
          ? (variables: unknown) => success(variables as V)
          : success
        : undefined,
    },
    mutationFn: (variables: V) => {
      const { path, method, body } = request(variables)
      return api<unknown>(`/spaces/${spaceId}/tasks/${path}`, { method, body })
    },
    onSuccess: refresh,
  })
}

export function useAddSubtask(spaceId: string, taskId: string) {
  return useTaskAction(
    spaceId,
    (body: Record<string, unknown>) => ({
      path: `${taskId}/subtasks`,
      method: 'POST' as const,
      body,
    }),
    'Sous-tâche ajoutée',
  )
}

export function useAddComment(spaceId: string, taskId: string) {
  return useTaskAction(
    spaceId,
    (body: { body: string; mentions: string[] }) => ({
      path: `${taskId}/comments`,
      method: 'POST' as const,
      body,
    }),
    'Commentaire publié',
  )
}

export function useDeleteComment(spaceId: string, taskId: string) {
  return useTaskAction(spaceId, (commentId: string) => ({
    path: `${taskId}/comments/${commentId}`,
    method: 'DELETE' as const,
  }))
}

export function useFollowTask(spaceId: string, taskId: string) {
  return useTaskAction(
    spaceId,
    (follow: boolean) => ({
      path: `${taskId}/follow`,
      method: follow ? ('POST' as const) : ('DELETE' as const),
    }),
    (follow) => (follow ? 'Vous suivez cette tâche' : 'Vous ne suivez plus cette tâche'),
  )
}

export function useAddDependency(spaceId: string, taskId: string) {
  return useTaskAction(
    spaceId,
    (dependsOnId: string) => ({
      path: `${taskId}/dependencies`,
      method: 'POST' as const,
      body: { depends_on_id: dependsOnId },
    }),
    'Dépendance ajoutée',
  )
}

export function useRemoveDependency(spaceId: string, taskId: string) {
  return useTaskAction(spaceId, (dependsOnId: string) => ({
    path: `${taskId}/dependencies/${dependsOnId}`,
    method: 'DELETE' as const,
  }))
}

// ---------- Accès à un projet (lot C) ----------

export function useProjectAccess(spaceId: string, projectId: string) {
  return useQuery({
    queryKey: [...projectKeys.one(spaceId, projectId), 'access'],
    queryFn: () => api<ProjectAccess>(`/spaces/${spaceId}/projects/${projectId}/access`),
  })
}

export function useSetProjectAccess(spaceId: string, projectId: string) {
  const refresh = useRefreshProjects(spaceId)
  return useMutation({
    meta: { success: 'Accès enregistrés' },
    mutationFn: (body: {
      private: boolean
      members: { member_id: string; role: 'contributor' | 'reader' }[]
    }) =>
      api<ProjectAccess>(`/spaces/${spaceId}/projects/${projectId}/access`, {
        method: 'PUT',
        body,
      }),
    onSuccess: refresh,
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
    meta: { success: 'Projet lié' },
    mutationFn: (body: { project_id: string; note: string | null }) =>
      api<ProjectLink>(`/spaces/${spaceId}/projects/${projectId}/links`, { method: 'POST', body }),
    onSettled: refresh,
  })
}

export function useRemoveProjectLink(spaceId: string, projectId: string) {
  const refresh = useRefreshProjects(spaceId)
  return useMutation({
    meta: { success: 'Lien retiré' },
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
    meta: { success: 'Document ajouté' },
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

/** Joint un fichier à une tâche (il rejoint aussi le dossier du projet). */
export function useUploadTaskDocument(spaceId: string, taskId: string) {
  const refresh = useRefreshProjects(spaceId)
  return useMutation({
    meta: { success: 'Fichier joint' },
    mutationFn: (file: File) => {
      const body = new FormData()
      body.append('file', file)
      return api<DocumentItem>(`/spaces/${spaceId}/tasks/${taskId}/documents`, {
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
    meta: { success: 'Nouvelle version ajoutée' },
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
    meta: { success: 'Document retiré' },
    mutationFn: (documentId: string) =>
      api<DocumentItem>(`/spaces/${spaceId}/documents/${documentId}/archive`, { method: 'POST' }),
    onSettled: refresh,
  })
}

export function downloadUrl(spaceId: string, documentId: string) {
  return `/api/spaces/${spaceId}/documents/${documentId}/download`
}

// ---------- Modèles de projet ----------

const templateKeys = (spaceId: string) => ['space', spaceId, 'templates'] as const

export function useTemplates(spaceId: string, enabled = true) {
  return useQuery({
    queryKey: templateKeys(spaceId),
    queryFn: () => api<ProjectTemplate[]>(`/spaces/${spaceId}/templates`),
    enabled,
  })
}

export function useCreateTemplate(spaceId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    meta: { success: 'Modèle enregistré' },
    mutationFn: (body: { project_id: string; name: string; description?: string | null }) =>
      api<ProjectTemplate>(`/spaces/${spaceId}/templates`, { method: 'POST', body }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: templateKeys(spaceId) }),
  })
}

export function useUpdateTemplate(spaceId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    meta: { success: 'Modèle renommé' },
    mutationFn: ({ id, ...body }: { id: string; version: number; name: string }) =>
      api<ProjectTemplate>(`/spaces/${spaceId}/templates/${id}`, { method: 'PATCH', body }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: templateKeys(spaceId) }),
  })
}

export function useDeleteTemplate(spaceId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    meta: { success: 'Modèle supprimé' },
    mutationFn: (id: string) =>
      api<void>(`/spaces/${spaceId}/templates/${id}`, { method: 'DELETE' }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: templateKeys(spaceId) }),
  })
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
    meta: { success: 'Alertes marquées comme lues' },
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
    meta: { success: 'Préférences enregistrées' },
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
    meta: { success: 'Profil enregistré' },
    mutationFn: (body: { display_name: string }) => api<Me>('/auth/me', { method: 'PATCH', body }),
    onSuccess: (me) => queryClient.setQueryData(keys.me, me),
  })
}

export function useChangePassword() {
  return useMutation({
    meta: { success: 'Mot de passe changé' },
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
    meta: { success: 'Mise à jour appliquée au projet' },
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
    meta: { success: 'Proposition écartée' },
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
    meta: { success: 'Fichier ajouté au dossier du projet' },
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

// ---------- Assistant IA (lot E) ----------

const aiKeys = {
  status: (spaceId: string) => ['space', spaceId, 'ai', 'status'] as const,
  list: (spaceId: string) => ['space', spaceId, 'ai', 'conversations'] as const,
  one: (spaceId: string, id: string) => ['space', spaceId, 'ai', 'conversations', id] as const,
}

export function useAiStatus(spaceId: string) {
  return useQuery({
    queryKey: aiKeys.status(spaceId),
    queryFn: () => api<AiStatus>(`/spaces/${spaceId}/ai/status`),
  })
}

export function useToggleAi(spaceId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (enabled: boolean) =>
      api<AiStatus>(`/spaces/${spaceId}/ai/status`, { method: 'PUT', body: { enabled } }),
    onSuccess: (data) => queryClient.setQueryData(aiKeys.status(spaceId), data),
  })
}

export function useAiConversations(spaceId: string, enabled = true) {
  return useQuery({
    queryKey: aiKeys.list(spaceId),
    queryFn: () => api<AiConversationSummary[]>(`/spaces/${spaceId}/ai/conversations`),
    enabled,
  })
}

/** Interroge la conversation toutes les 1,5 s tant que l'assistant prépare sa réponse. */
export function useAiConversation(spaceId: string, id: string | null) {
  const queryClient = useQueryClient()
  return useQuery({
    queryKey: aiKeys.one(spaceId, id ?? ''),
    queryFn: async () => {
      const data = await api<AiConversation>(`/spaces/${spaceId}/ai/conversations/${id}`)
      if (data.status === 'idle') {
        void queryClient.invalidateQueries({ queryKey: aiKeys.list(spaceId), exact: true })
        void queryClient.invalidateQueries({ queryKey: aiKeys.status(spaceId) })
      }
      return data
    },
    enabled: Boolean(id),
    refetchInterval: (query) => (query.state.data?.status === 'thinking' ? 1500 : false),
  })
}

export function useSendAiMessage(spaceId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ conversationId, text }: { conversationId: string | null; text: string }) =>
      conversationId
        ? api<AiConversation>(`/spaces/${spaceId}/ai/conversations/${conversationId}/messages`, {
            method: 'POST',
            body: { text },
          })
        : api<AiConversation>(`/spaces/${spaceId}/ai/conversations`, {
            method: 'POST',
            body: { text },
          }),
    onSuccess: (data) => {
      queryClient.setQueryData(aiKeys.one(spaceId, data.id), data)
      void queryClient.invalidateQueries({ queryKey: aiKeys.list(spaceId), exact: true })
    },
  })
}

export function useDeleteAiConversation(spaceId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    meta: { success: 'Conversation supprimée' },
    mutationFn: (id: string) =>
      api<void>(`/spaces/${spaceId}/ai/conversations/${id}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: aiKeys.list(spaceId), exact: true }),
  })
}

export function useDecideAiAction(spaceId: string, conversationId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: 'apply' | 'reject' }) =>
      api<AiAction>(`/spaces/${spaceId}/ai/actions/${id}/${decision}`, { method: 'POST' }),
    onSettled: () => {
      // Un changement appliqué peut toucher projets, tâches, tableau de bord et alertes.
      // Sans attendre : « Appliquer tout » enchaîne aussitôt la proposition suivante.
      void queryClient.invalidateQueries({ queryKey: keys.space(spaceId) })
    },
    onSuccess: (action) =>
      queryClient.setQueryData<AiConversation>(aiKeys.one(spaceId, conversationId), (old) =>
        old
          ? {
              ...old,
              turns: old.turns.map((t) => ({
                ...t,
                actions: (t.actions ?? []).map((a) => (a.id === action.id ? action : a)),
              })),
            }
          : old,
      ),
  })
}

// ---------- Sections d'un projet (étape F1) ----------

const sectionKey = (spaceId: string, projectId: string) =>
  [...projectKeys.one(spaceId, projectId), 'sections'] as const

export function useSections(spaceId: string, projectId: string) {
  return useQuery({
    queryKey: sectionKey(spaceId, projectId),
    queryFn: () => api<Section[]>(`/spaces/${spaceId}/projects/${projectId}/sections`),
  })
}

/** Toute écriture sur les sections recharge le projet (sections, tâches, historique). */
function useSectionMutation<V, R>(
  spaceId: string,
  projectId: string,
  success: string | null,
  fn: (vars: V) => Promise<R>,
) {
  const queryClient = useQueryClient()
  return useMutation({
    meta: success ? { success } : undefined,
    mutationFn: fn,
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: projectKeys.one(spaceId, projectId) }),
  })
}

export function useCreateSection(spaceId: string, projectId: string) {
  return useSectionMutation(spaceId, projectId, 'Section ajoutée', (title: string) =>
    api<Section>(`/spaces/${spaceId}/projects/${projectId}/sections`, {
      method: 'POST',
      body: { title },
    }),
  )
}

export function useDefaultSections(spaceId: string, projectId: string) {
  return useSectionMutation(spaceId, projectId, 'Sections types ajoutées', () =>
    api<Section[]>(`/spaces/${spaceId}/projects/${projectId}/sections/defaults`, {
      method: 'POST',
    }),
  )
}

export function useRenameSection(spaceId: string, projectId: string) {
  return useSectionMutation(
    spaceId,
    projectId,
    'Section renommée',
    ({ section, title }: { section: Section; title: string }) =>
      api<Section>(`/spaces/${spaceId}/sections/${section.id}`, {
        method: 'PATCH',
        body: { version: section.version, title },
      }),
  )
}

export function useReorderSections(spaceId: string, projectId: string) {
  return useSectionMutation(spaceId, projectId, null, (ids: string[]) =>
    api<Section[]>(`/spaces/${spaceId}/projects/${projectId}/sections/order`, {
      method: 'PUT',
      body: { ids },
    }),
  )
}

export function useArchiveSection(spaceId: string, projectId: string) {
  return useSectionMutation(
    spaceId,
    projectId,
    'Section archivée',
    ({ id, target, keep }: { id: string; target: string | null; keep: boolean }) =>
      api<Section>(`/spaces/${spaceId}/sections/${id}/archive`, {
        method: 'POST',
        body: { move_open_tasks_to: target, keep_tasks: keep },
      }),
  )
}

export function useRestoreSection(spaceId: string, projectId: string) {
  return useSectionMutation(spaceId, projectId, 'Section restaurée', (id: string) =>
    api<Section>(`/spaces/${spaceId}/sections/${id}/restore`, { method: 'POST' }),
  )
}

// ---------- Jalons (étape F2) ----------

const milestoneKey = (spaceId: string, projectId: string) =>
  [...projectKeys.one(spaceId, projectId), 'milestones'] as const

export function useMilestones(spaceId: string, projectId: string) {
  return useQuery({
    queryKey: milestoneKey(spaceId, projectId),
    queryFn: () => api<Milestone[]>(`/spaces/${spaceId}/projects/${projectId}/milestones`),
  })
}

/** Écrire un jalon recharge le projet (jalons, historique) et les alertes. */
function useMilestoneMutation<V>(
  spaceId: string,
  projectId: string,
  success: string,
  fn: (vars: V) => Promise<Milestone>,
) {
  const queryClient = useQueryClient()
  return useMutation({
    meta: { success },
    mutationFn: fn,
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: projectKeys.one(spaceId, projectId) }),
        queryClient.invalidateQueries({ queryKey: ['space', spaceId, 'alerts'] }),
      ]),
  })
}

export function useCreateMilestone(spaceId: string, projectId: string) {
  return useMilestoneMutation(spaceId, projectId, 'Jalon ajouté', (body: Record<string, unknown>) =>
    api<Milestone>(`/spaces/${spaceId}/projects/${projectId}/milestones`, {
      method: 'POST',
      body,
    }),
  )
}

export function useUpdateMilestone(spaceId: string, projectId: string) {
  return useMilestoneMutation(
    spaceId,
    projectId,
    'Jalon enregistré',
    ({ milestone, changes }: { milestone: Milestone; changes: Record<string, unknown> }) =>
      api<Milestone>(`/spaces/${spaceId}/milestones/${milestone.id}`, {
        method: 'PATCH',
        body: { ...changes, version: milestone.version },
      }),
  )
}

export function useCloseMilestone(spaceId: string, projectId: string) {
  return useMilestoneMutation(
    spaceId,
    projectId,
    'Jalon clôturé',
    ({ milestone, state, note }: { milestone: Milestone; state: string; note: string | null }) =>
      api<Milestone>(`/spaces/${spaceId}/milestones/${milestone.id}/close`, {
        method: 'POST',
        body: { version: milestone.version, state, note },
      }),
  )
}

export function useReopenMilestone(spaceId: string, projectId: string) {
  return useMilestoneMutation(spaceId, projectId, 'Jalon rouvert', (milestone: Milestone) =>
    api<Milestone>(`/spaces/${spaceId}/milestones/${milestone.id}/reopen`, {
      method: 'POST',
      body: { version: milestone.version },
    }),
  )
}

export function useMilestoneTasks(spaceId: string, projectId: string) {
  return useMilestoneMutation(
    spaceId,
    projectId,
    'Tâches liées enregistrées',
    ({ milestone, taskIds }: { milestone: Milestone; taskIds: string[] }) =>
      api<Milestone>(`/spaces/${spaceId}/milestones/${milestone.id}/tasks`, {
        method: 'PUT',
        body: { version: milestone.version, task_ids: taskIds },
      }),
  )
}

// ---------- Décisions et réunions (étape F3) ----------

const decisionKeys = {
  all: (spaceId: string) => ['space', spaceId, 'decisions'] as const,
  meetings: (spaceId: string) => ['space', spaceId, 'meetings'] as const,
}

export function useDecisions(spaceId: string, filters: { project_id?: string } = {}) {
  const query = new URLSearchParams(filters as Record<string, string>).toString()
  return useQuery({
    queryKey: [...decisionKeys.all(spaceId), filters],
    queryFn: () => api<Decision[]>(`/spaces/${spaceId}/decisions${query ? `?${query}` : ''}`),
  })
}

export function useMeetings(spaceId: string) {
  return useQuery({
    queryKey: decisionKeys.meetings(spaceId),
    queryFn: () => api<Meeting[]>(`/spaces/${spaceId}/meetings`),
  })
}

/** Écrire une décision ou une réunion recharge le registre, les réunions, les projets
 * (tâches créées, historique) et les alertes. */
function useDecisionMutation<V, R>(spaceId: string, success: string, fn: (v: V) => Promise<R>) {
  const queryClient = useQueryClient()
  return useMutation({
    meta: { success },
    mutationFn: fn,
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: decisionKeys.all(spaceId) }),
        queryClient.invalidateQueries({ queryKey: decisionKeys.meetings(spaceId) }),
        queryClient.invalidateQueries({ queryKey: projectKeys.all(spaceId) }),
        queryClient.invalidateQueries({ queryKey: ['space', spaceId, 'alerts'] }),
      ]),
  })
}

export function useCreateDecision(spaceId: string) {
  return useDecisionMutation(spaceId, 'Décision consignée', (body: Record<string, unknown>) =>
    api<Decision>(`/spaces/${spaceId}/decisions`, { method: 'POST', body }),
  )
}

export function useUpdateDecision(spaceId: string) {
  return useDecisionMutation(
    spaceId,
    'Décision enregistrée',
    ({ decision, changes }: { decision: Decision; changes: Record<string, unknown> }) =>
      api<Decision>(`/spaces/${spaceId}/decisions/${decision.id}`, {
        method: 'PATCH',
        body: { ...changes, version: decision.version },
      }),
  )
}

export function useDecisionAction(spaceId: string, success: string) {
  return useDecisionMutation(
    spaceId,
    success,
    ({
      decision,
      action,
      body = {},
    }: {
      decision: Decision
      action: 'validate' | 'accept' | 'close' | 'reopen' | 'tasks'
      body?: Record<string, unknown>
    }) =>
      api<Decision>(`/spaces/${spaceId}/decisions/${decision.id}/${action}`, {
        method: 'POST',
        body: { ...body, version: decision.version },
      }),
  )
}

export function useCreateMeeting(spaceId: string) {
  return useDecisionMutation(spaceId, 'Réunion ajoutée', (body: Record<string, unknown>) =>
    api<Meeting>(`/spaces/${spaceId}/meetings`, { method: 'POST', body }),
  )
}

export function useUpdateMeeting(spaceId: string) {
  return useDecisionMutation(
    spaceId,
    'Relevé enregistré',
    ({ meeting, changes }: { meeting: Meeting; changes: Record<string, unknown> }) =>
      api<Meeting>(`/spaces/${spaceId}/meetings/${meeting.id}`, {
        method: 'PATCH',
        body: { ...changes, version: meeting.version },
      }),
  )
}

// ---------- Suppression définitive de projets (propriétaire) ----------

export function usePurgeProjects(spaceId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    meta: { success: 'Projets supprimés définitivement' },
    mutationFn: (projectIds: string[]) =>
      api<{ deleted: number; titles: string[] }>(`/spaces/${spaceId}/projects/purge`, {
        method: 'POST',
        body: { project_ids: projectIds, confirm: 'SUPPRIMER' },
      }),
    // Tout l'espace peut changer : projets, tâches, décisions, alertes, documents.
    onSettled: () => queryClient.invalidateQueries({ queryKey: keys.space(spaceId) }),
  })
}

// ---------- Champs personnalisés (étape F4) ----------

const fieldKeys = {
  all: (spaceId: string) => ['space', spaceId, 'custom-fields'] as const,
  values: (spaceId: string) => ['space', spaceId, 'custom-values'] as const,
  project: (spaceId: string, projectId: string) =>
    [...projectKeys.one(spaceId, projectId), 'custom-fields'] as const,
}

export function useCustomFields(spaceId: string, enabled = true) {
  return useQuery({
    queryKey: fieldKeys.all(spaceId),
    queryFn: () => api<CustomField[]>(`/spaces/${spaceId}/custom-fields`),
    enabled,
  })
}

/** Valeurs des champs de projet, par projet (filtres de la liste des projets). */
export function useCustomValues(spaceId: string, enabled = true) {
  return useQuery({
    queryKey: fieldKeys.values(spaceId),
    queryFn: () => api<Record<string, Record<string, unknown>>>(`/spaces/${spaceId}/custom-values`),
    enabled,
  })
}

export function useProjectFields(spaceId: string, projectId: string, enabled = true) {
  return useQuery({
    queryKey: fieldKeys.project(spaceId, projectId),
    queryFn: () => api<ProjectFields>(`/spaces/${spaceId}/projects/${projectId}/custom-fields`),
    enabled,
  })
}

function useFieldMutation<V, R>(spaceId: string, success: string | null, fn: (v: V) => Promise<R>) {
  const queryClient = useQueryClient()
  return useMutation({
    meta: success ? { success } : undefined,
    mutationFn: fn,
    // Catalogue, valeurs par projet et fiches concernées (pas tout l'espace).
    onSettled: () => {
      void queryClient.invalidateQueries({
        queryKey: ['space', spaceId],
        predicate: (q) =>
          q.queryKey.includes('custom-fields') || q.queryKey.includes('custom-values'),
      })
    },
  })
}

export type FieldDraft = {
  label: string
  target: 'project' | 'task'
  type: CustomField['type']
  description?: string | null
  required?: boolean
  project_id?: string | null
  options?: string[]
  config?: Record<string, unknown>
}

export function useCreateField(spaceId: string) {
  return useFieldMutation(spaceId, 'Champ ajouté', (body: FieldDraft) =>
    api<CustomField>(`/spaces/${spaceId}/custom-fields`, { method: 'POST', body }),
  )
}

export function useUpdateField(spaceId: string) {
  return useFieldMutation(
    spaceId,
    'Champ enregistré',
    ({ field, ...body }: { field: CustomField } & Record<string, unknown>) =>
      api<CustomField>(`/spaces/${spaceId}/custom-fields/${field.id}`, {
        method: 'PATCH',
        body: { version: field.version, ...body },
      }),
  )
}

export function useArchiveField(spaceId: string) {
  return useFieldMutation(spaceId, null, ({ id, restore }: { id: string; restore: boolean }) =>
    api<CustomField>(`/spaces/${spaceId}/custom-fields/${id}/${restore ? 'restore' : 'archive'}`, {
      method: 'POST',
    }),
  )
}

export function useReorderFields(spaceId: string) {
  return useFieldMutation(spaceId, null, (ids: string[]) =>
    api<CustomField[]>(`/spaces/${spaceId}/custom-fields/order`, { method: 'PUT', body: { ids } }),
  )
}

export function previewFieldType(spaceId: string, fieldId: string, type: string) {
  return api<TypePreview>(
    `/spaces/${spaceId}/custom-fields/${fieldId}/type-preview?type=${encodeURIComponent(type)}`,
  )
}

export function useSaveCustomValues(spaceId: string, projectId: string) {
  return useFieldMutation(
    spaceId,
    'Champs enregistrés',
    ({ taskId, values }: { taskId?: string | null; values: Record<string, unknown> }) =>
      api<ProjectFields>(
        taskId
          ? `/spaces/${spaceId}/tasks/${taskId}/custom-values`
          : `/spaces/${spaceId}/projects/${projectId}/custom-values`,
        { method: 'PUT', body: { values } },
      ),
  )
}

export function useHideFields(spaceId: string, projectId: string) {
  return useFieldMutation(spaceId, null, (fieldIds: string[]) =>
    api<ProjectFields>(`/spaces/${spaceId}/projects/${projectId}/custom-fields/hidden`, {
      method: 'PUT',
      body: { field_ids: fieldIds },
    }),
  )
}

// ---------- Routines et « Ma journée / Ma semaine » (étape F5) ----------

const routineKeys = {
  all: (spaceId: string) => ['space', spaceId, 'routines'] as const,
  profiles: (spaceId: string) => ['space', spaceId, 'routines', 'profiles'] as const,
  occurrences: (spaceId: string, params: Record<string, string>) =>
    ['space', spaceId, 'routines', 'occurrences', params] as const,
  agenda: (spaceId: string, start: string, end: string) =>
    ['space', spaceId, 'routines', 'agenda', start, end] as const,
}

export function useRoutines(spaceId: string) {
  return useQuery({
    queryKey: routineKeys.all(spaceId),
    queryFn: () => api<Routine[]>(`/spaces/${spaceId}/routines`),
  })
}

export function useRoutineProfiles(spaceId: string, enabled = true) {
  return useQuery({
    queryKey: routineKeys.profiles(spaceId),
    queryFn: () => api<RoutineProfile[]>(`/spaces/${spaceId}/routines/profiles`),
    enabled,
  })
}

export function useOccurrences(spaceId: string, params: Record<string, string>, enabled = true) {
  const query = new URLSearchParams(params).toString()
  return useQuery({
    queryKey: routineKeys.occurrences(spaceId, params),
    queryFn: () => api<Occurrence[]>(`/spaces/${spaceId}/routine-occurrences?${query}`),
    enabled,
  })
}

export function useAgenda(spaceId: string, start: string, end: string) {
  return useQuery({
    queryKey: routineKeys.agenda(spaceId, start, end),
    queryFn: () => api<Agenda>(`/spaces/${spaceId}/agenda?start=${start}&end=${end}`),
  })
}

/** Toute écriture sur une routine recharge les routines, occurrences et la journée. Une suite
 * (tâche, décision) recharge aussi le reste de l'espace. */
function useRoutineMutation<V, R>(
  spaceId: string,
  success: string | null,
  fn: (v: V) => Promise<R>,
  everything = false,
) {
  const queryClient = useQueryClient()
  return useMutation({
    meta: success ? { success } : undefined,
    mutationFn: fn,
    onSettled: () => {
      void queryClient.invalidateQueries({
        queryKey: everything ? ['space', spaceId] : routineKeys.all(spaceId),
      })
    },
  })
}

export function useCreateRoutine(spaceId: string) {
  return useRoutineMutation(spaceId, 'Routine créée', (body: Record<string, unknown>) =>
    api<Routine>(`/spaces/${spaceId}/routines`, { method: 'POST', body }),
  )
}

export function useAddProfiles(spaceId: string) {
  return useRoutineMutation(spaceId, 'Routines ajoutées', (keys: string[]) =>
    api<Routine[]>(`/spaces/${spaceId}/routines/profiles`, { method: 'POST', body: { keys } }),
  )
}

export function useUpdateRoutine(spaceId: string) {
  return useRoutineMutation(
    spaceId,
    'Routine enregistrée',
    ({ routine, ...body }: { routine: Routine } & Record<string, unknown>) =>
      api<Routine>(`/spaces/${spaceId}/routines/${routine.id}`, {
        method: 'PATCH',
        body: { version: routine.version, ...body },
      }),
  )
}

export function useRoutineAction(spaceId: string) {
  return useRoutineMutation(
    spaceId,
    null,
    ({
      id,
      action,
      reason,
    }: {
      id: string
      action: 'pause' | 'resume' | 'archive' | 'restore'
      reason?: string
    }) =>
      api<Routine>(`/spaces/${spaceId}/routines/${id}/${action}`, {
        method: 'POST',
        body: action === 'archive' ? { reason } : undefined,
      }),
  )
}

export function useUpdateOccurrence(spaceId: string) {
  return useRoutineMutation(
    spaceId,
    null,
    ({ occurrence, ...body }: { occurrence: Occurrence } & Record<string, unknown>) =>
      api<Occurrence>(`/spaces/${spaceId}/routine-occurrences/${occurrence.id}`, {
        method: 'PATCH',
        body: { version: occurrence.version, ...body },
      }),
  )
}

export function useCloseOccurrence(spaceId: string) {
  return useRoutineMutation(
    spaceId,
    null,
    ({ occurrence, ...body }: { occurrence: Occurrence } & Record<string, unknown>) =>
      api<Occurrence>(`/spaces/${spaceId}/routine-occurrences/${occurrence.id}/close`, {
        method: 'POST',
        body: { version: occurrence.version, ...body },
      }),
  )
}

export function useReopenOccurrence(spaceId: string) {
  return useRoutineMutation(spaceId, null, (occurrence: Occurrence) =>
    api<Occurrence>(`/spaces/${spaceId}/routine-occurrences/${occurrence.id}/reopen`, {
      method: 'POST',
      body: { version: occurrence.version },
    }),
  )
}

export function useFollowUp(spaceId: string) {
  return useRoutineMutation(
    spaceId,
    'Suite créée',
    ({ occurrenceId, ...body }: { occurrenceId: string } & Record<string, unknown>) =>
      api<Occurrence>(`/spaces/${spaceId}/routine-occurrences/${occurrenceId}/follow-ups`, {
        method: 'POST',
        body,
      }),
    true,
  )
}

// ---------- Pilotage, relations et contrôles d'événement (étape F6) ----------

const pilotKeys = {
  indicators: (spaceId: string, start: string, end: string) =>
    ['space', spaceId, 'pilotage', 'indicators', start, end] as const,
  capacity: (spaceId: string) => ['space', spaceId, 'pilotage', 'capacity'] as const,
  relations: (spaceId: string) => ['space', spaceId, 'pilotage', 'relations'] as const,
  encounters: (spaceId: string) => ['space', spaceId, 'pilotage', 'encounters'] as const,
  controls: (spaceId: string, projectId: string) =>
    [...projectKeys.one(spaceId, projectId), 'event-controls'] as const,
}

export function useIndicators(spaceId: string, start: string, end: string) {
  return useQuery({
    queryKey: pilotKeys.indicators(spaceId, start, end),
    queryFn: () => api<Indicators>(`/spaces/${spaceId}/indicators?start=${start}&end=${end}`),
  })
}

function usePilotMutation<V, R>(spaceId: string, success: string | null, fn: (v: V) => Promise<R>) {
  const queryClient = useQueryClient()
  return useMutation({
    meta: success ? { success } : undefined,
    mutationFn: fn,
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ['space', spaceId, 'pilotage'] })
    },
  })
}

export function useSetTargets(spaceId: string) {
  return usePilotMutation(spaceId, 'Cibles enregistrées', (targets: Record<string, number>) =>
    api<Indicators>(`/spaces/${spaceId}/indicators/targets`, { method: 'PUT', body: { targets } }),
  )
}

export function useCapacity(spaceId: string) {
  return useQuery({
    queryKey: pilotKeys.capacity(spaceId),
    queryFn: () => api<Capacity>(`/spaces/${spaceId}/capacity?weeks=6`),
  })
}

export function useSetCapacity(spaceId: string) {
  return usePilotMutation(
    spaceId,
    'Capacité enregistrée',
    ({ memberId, hours, note }: { memberId: string; hours: number | null; note?: string | null }) =>
      api<Capacity>(`/spaces/${spaceId}/capacity/${memberId}`, {
        method: 'PUT',
        body: { hours_per_week: hours, note: note ?? null },
      }),
  )
}

export function useRelations(spaceId: string) {
  return useQuery({
    queryKey: pilotKeys.relations(spaceId),
    queryFn: () => api<Relation[]>(`/spaces/${spaceId}/relations`),
  })
}

export function useSaveRelation(spaceId: string) {
  return usePilotMutation(
    spaceId,
    'Relation enregistrée',
    ({ relation, ...body }: { relation?: Relation } & Record<string, unknown>) =>
      relation
        ? api<Relation>(`/spaces/${spaceId}/relations/${relation.id}`, {
            method: 'PATCH',
            body: { version: relation.version, ...body },
          })
        : api<Relation>(`/spaces/${spaceId}/relations`, { method: 'POST', body }),
  )
}

export function useEncounters(spaceId: string) {
  return useQuery({
    queryKey: pilotKeys.encounters(spaceId),
    queryFn: () => api<Encounter[]>(`/spaces/${spaceId}/encounters`),
  })
}

export function useSaveEncounter(spaceId: string) {
  return usePilotMutation(
    spaceId,
    null,
    ({ encounter, ...body }: { encounter?: Encounter } & Record<string, unknown>) =>
      encounter
        ? api<Encounter>(`/spaces/${spaceId}/encounters/${encounter.id}`, {
            method: 'PATCH',
            body: { version: encounter.version, ...body },
          })
        : api<Encounter>(`/spaces/${spaceId}/encounters`, { method: 'POST', body }),
  )
}

export function useCloseEncounter(spaceId: string) {
  return usePilotMutation(
    spaceId,
    null,
    ({ encounter, reopen, reason }: { encounter: Encounter; reopen?: boolean; reason?: string }) =>
      api<Encounter>(
        `/spaces/${spaceId}/encounters/${encounter.id}/${reopen ? 'reopen' : 'close'}`,
        { method: 'POST', body: { version: encounter.version, reason: reason || null } },
      ),
  )
}

export function useEventControls(spaceId: string, projectId: string, enabled = true) {
  return useQuery({
    queryKey: pilotKeys.controls(spaceId, projectId),
    queryFn: () => api<EventControl[]>(`/spaces/${spaceId}/projects/${projectId}/event-controls`),
    enabled,
  })
}

export function useSetEventControl(spaceId: string, projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ key, done, note }: { key: string; done: boolean; note?: string | null }) =>
      api<EventControl[]>(`/spaces/${spaceId}/projects/${projectId}/event-controls/${key}`, {
        method: 'PUT',
        body: { done, note: note ?? null },
      }),
    onSuccess: (data) => queryClient.setQueryData(pilotKeys.controls(spaceId, projectId), data),
  })
}

export function useSaveArbitration(spaceId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ decision, ...body }: { decision: Decision } & Record<string, unknown>) =>
      api<Decision>(`/spaces/${spaceId}/decisions/${decision.id}/arbitration`, {
        method: 'PUT',
        body: { version: decision.version, ...body },
      }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: decisionKeys.all(spaceId) })
    },
  })
}
