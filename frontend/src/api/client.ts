import type { components } from './schema'

type Schemas = components['schemas']
export type Me = Schemas['MeOut']
export type SpaceSummary = Schemas['SpaceSummary']
export type Space = Schemas['SpaceOut']
export type Member = Schemas['MemberOut']
export type Role = Schemas['Role']
export type InvitationLink = Schemas['InvitationLink']
export type InvitationInfo = Schemas['InvitationInfo']

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export async function api<T>(path: string, options: { method?: Method; body?: unknown } = {}) {
  const method = options.method ?? 'GET'
  const headers: Record<string, string> = {}
  if (method !== 'GET') headers['X-PILOT-CSRF'] = '1' // exigé par l'API pour toute écriture
  const isForm = options.body instanceof FormData
  if (options.body !== undefined && !isForm) headers['Content-Type'] = 'application/json'

  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers,
      credentials: 'same-origin',
      body:
        options.body === undefined
          ? undefined
          : isForm
            ? (options.body as FormData)
            : JSON.stringify(options.body),
    })
  } catch {
    throw new ApiError(0, 'PILOT ne répond pas. Vérifiez votre connexion internet et réessayez.')
  }

  if (response.status === 204) return undefined as T
  const data: unknown = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(response.status, detailOf(data, response.status))
  return data as T
}

function detailOf(data: unknown, status: number): string {
  const detail = (data as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (status === 422) return 'Certaines informations sont invalides. Vérifiez les champs.'
  return 'Une erreur est survenue. Réessayez dans un instant.'
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Une erreur est survenue.'
}

export const ROLE_LABELS: Record<Role, string> = {
  owner: 'Propriétaire',
  contributor: 'Contributeur',
  reader: 'Lecteur',
}

export type Project = Schemas['ProjectOut']
export type Task = Schemas['TaskOut']
export type TaskDetail = Schemas['TaskDetail']
export type TaskRef = Schemas['TaskRef']
export type TaskComment = Schemas['CommentOut']
export type ProjectLink = Schemas['ProjectLinkOut']
export type HistoryEntry = Schemas['HistoryEntry']
export type PersonRef = Schemas['PersonRef']
export type DocumentItem = Schemas['DocumentOut']
export type AlertItem = Schemas['AlertOut']
export type AlertList = Schemas['AlertList']
export type AlertPreferences = Schemas['AlertPreferenceOut']
export type UpdateRequest = Schemas['UpdateRequestOut']
export type Proposal = Schemas['ProposalOut']
export type ProposalChange = Schemas['ProposalChangeOut']
export type UpdateSource = Schemas['UpdateSourceOut']
export type ImportResult = Schemas['ImportResult']
