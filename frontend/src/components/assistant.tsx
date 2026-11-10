import { Fragment, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Link } from 'react-router'
import { errorMessage, type AiAction, type AiConversation, type Space } from '../api/client'
import {
  useAiConversation,
  useAiConversations,
  useAiStatus,
  useDecideAiAction,
  useDeleteAiConversation,
  useSendAiMessage,
  useToggleAi,
} from '../api/queries'
import { formatMoment } from '../labels'
import { Alert, Skeleton, StatusPill, type Tone } from './ui'

const ACTION_STATE: Record<AiAction['state'], { label: string; tone: Tone }> = {
  pending: { label: 'À valider', tone: 'info' },
  applied: { label: 'Appliquée', tone: 'ok' },
  rejected: { label: 'Refusée', tone: 'neutral' },
  conflict: { label: 'En conflit', tone: 'danger' },
  failed: { label: 'Non appliquée', tone: 'danger' },
}

const SUGGESTIONS = [
  'Quelles tâches sont en retard ?',
  'Qu’est-ce que je dois faire cette semaine ?',
  'Fais le point sur un projet',
  'Crée une tâche dans un projet',
]

/** Texte de l'assistant : paragraphes, listes « - » et **gras**, sans HTML interprété. */
function inline(text: string): ReactNode[] {
  return text
    .split(/(\*\*[^*]+\*\*)/g)
    .map((part, i) =>
      part.startsWith('**') && part.endsWith('**') && part.length > 4 ? (
        <strong key={i}>{part.slice(2, -2)}</strong>
      ) : (
        <Fragment key={i}>{part}</Fragment>
      ),
    )
}

function RichText({ text }: { text: string }) {
  const blocks = text.split(/\n{2,}/)
  return (
    <>
      {blocks.map((block, i) => {
        const lines = block.split('\n')
        if (lines.every((l) => /^\s*([-•*]|\d+[.)])\s+/.test(l))) {
          return (
            <ul key={i}>
              {lines.map((l, j) => (
                <li key={j}>{inline(l.replace(/^\s*([-•*]|\d+[.)])\s+/, ''))}</li>
              ))}
            </ul>
          )
        }
        return (
          <p key={i}>
            {lines.map((l, j) => (
              <Fragment key={j}>
                {j > 0 && <br />}
                {inline(l.replace(/^#+\s*/, ''))}
              </Fragment>
            ))}
          </p>
        )
      })}
    </>
  )
}

function ActionCard({
  action,
  spaceId,
  conversationId,
}: {
  action: AiAction
  spaceId: string
  conversationId: string
}) {
  const decide = useDecideAiAction(spaceId, conversationId)
  const state = ACTION_STATE[action.state]
  const href = action.project_id
    ? `/espaces/${spaceId}/projets/${action.project_id}${action.task_id ? `?tache=${action.task_id}` : ''}`
    : null
  return (
    <article className={`ai-action ai-action--${action.state}`}>
      <header className="ai-action__head">
        <strong>{action.summary}</strong>
        <StatusPill tone={state.tone}>{state.label}</StatusPill>
      </header>
      {action.changes.length > 0 && (
        <dl className="ai-action__changes">
          {action.changes.map((c, i) => (
            <div key={i} className="ai-action__change">
              <dt>{c.field}</dt>
              <dd>
                {c.before && c.before !== '—' && (
                  <>
                    <span className="ai-action__before">{c.before}</span>
                    <span aria-hidden="true"> → </span>
                    <span className="visually-hidden"> devient </span>
                  </>
                )}
                <span className="ai-action__after">{c.after}</span>
              </dd>
            </div>
          ))}
        </dl>
      )}
      {action.result && action.state !== 'rejected' && (
        <p className="ai-action__result">{action.result}</p>
      )}
      {decide.isError && <Alert>{errorMessage(decide.error)}</Alert>}
      <div className="ai-action__buttons">
        {action.state === 'pending' && (
          <>
            <button
              type="button"
              className="button button--small button--primary"
              disabled={decide.isPending}
              onClick={() => decide.mutate({ id: action.id, decision: 'apply' })}
            >
              {decide.isPending ? 'Application…' : 'Appliquer'}
            </button>
            <button
              type="button"
              className="button button--small"
              disabled={decide.isPending}
              onClick={() => decide.mutate({ id: action.id, decision: 'reject' })}
            >
              Refuser
            </button>
          </>
        )}
        {href && action.state !== 'rejected' && (
          <Link className="link-button" to={href}>
            Ouvrir la fiche
          </Link>
        )}
      </div>
    </article>
  )
}

function ApplyAll({
  actions,
  spaceId,
  conversationId,
}: {
  actions: AiAction[]
  spaceId: string
  conversationId: string
}) {
  const decide = useDecideAiAction(spaceId, conversationId)
  const [busy, setBusy] = useState(false)
  const pending = actions.filter((a) => a.state === 'pending')
  if (pending.length < 2) return null
  async function run() {
    setBusy(true)
    try {
      // Une par une, dans l'ordre proposé : chacune passe les contrôles habituels.
      for (const action of pending) {
        await decide.mutateAsync({ id: action.id, decision: 'apply' }).catch(() => undefined)
      }
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="ai-apply-all">
      <button
        type="button"
        className="button button--small button--primary"
        disabled={busy}
        onClick={run}
      >
        {busy ? 'Application…' : `Appliquer les ${pending.length} propositions`}
      </button>
    </div>
  )
}

function Conversation({
  conversation,
  spaceId,
}: {
  conversation: AiConversation
  spaceId: string
}) {
  const end = useRef<HTMLDivElement>(null)
  const count = conversation.turns.length
  const thinking = conversation.status === 'thinking'
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'nearest' })
  }, [count, thinking])
  return (
    <div className="ai-thread" aria-live="polite">
      {conversation.turns.map((turn, i) => (
        <div
          key={i}
          className={`ai-turn ai-turn--${turn.role}${turn.error ? ' ai-turn--error' : ''}`}
        >
          <div className="ai-bubble">
            <span className="visually-hidden">
              {turn.role === 'user' ? 'Vous : ' : 'Assistant : '}
            </span>
            <RichText text={turn.text} />
          </div>
          {(turn.actions ?? []).length > 0 && (
            <div className="ai-actions">
              <ApplyAll
                actions={turn.actions ?? []}
                spaceId={spaceId}
                conversationId={conversation.id}
              />
              {(turn.actions ?? []).map((a) => (
                <ActionCard
                  key={a.id}
                  action={a}
                  spaceId={spaceId}
                  conversationId={conversation.id}
                />
              ))}
            </div>
          )}
        </div>
      ))}
      {thinking && (
        <div className="ai-turn ai-turn--assistant">
          <div className="ai-bubble ai-bubble--thinking" role="status">
            L’assistant réfléchit
            <span className="ai-dots" aria-hidden="true" />
          </div>
        </div>
      )}
      <div ref={end} />
    </div>
  )
}

function Composer({
  disabled,
  pending,
  onSend,
}: {
  disabled: boolean
  pending: boolean
  onSend: (text: string) => Promise<unknown>
}) {
  const [text, setText] = useState('')
  async function submit(event?: FormEvent) {
    event?.preventDefault()
    const value = text.trim()
    if (!value || disabled) return
    try {
      await onSend(value)
      setText('')
    } catch {
      // Le message reste dans la zone de saisie ; l'erreur s'affiche au-dessus.
    }
  }
  return (
    <form className="ai-composer" onSubmit={submit}>
      <label htmlFor="ai-input" className="visually-hidden">
        Votre message à l’assistant
      </label>
      <textarea
        id="ai-input"
        rows={2}
        maxLength={4000}
        placeholder="Posez une question ou demandez un changement… (Entrée pour envoyer)"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault()
            void submit()
          }
        }}
      />
      <button className="button button--primary" type="submit" disabled={disabled || !text.trim()}>
        {pending ? 'Envoi…' : 'Envoyer'}
      </button>
    </form>
  )
}

/** Assistant IA dans la page « Mises à jour » (lot E). */
export function AssistantPanel({ space }: { space: Space }) {
  const status = useAiStatus(space.id)
  const on = Boolean(status.data?.available && status.data.enabled)
  const list = useAiConversations(space.id, on)
  const [currentId, setCurrentId] = useState<string | null>(null)
  const conversation = useAiConversation(space.id, currentId)
  const send = useSendAiMessage(space.id)
  const remove = useDeleteAiConversation(space.id)

  if (status.isPending) return <Skeleton />
  if (status.isError) return <Alert>{errorMessage(status.error)}</Alert>
  const s = status.data
  if (!s.available) {
    return (
      <Alert tone="info">
        L’assistant n’est pas encore configuré sur le serveur : la clé Anthropic doit être ajoutée
        par l’administrateur.
      </Alert>
    )
  }
  if (!s.enabled) {
    return (
      <Alert tone="info">
        L’assistant est éteint pour cet espace.{' '}
        {s.can_toggle ? (
          <>
            Vous pouvez l’allumer dans{' '}
            <Link to={`/espaces/${space.id}/parametres`}>Paramètres → Assistant IA</Link>.
          </>
        ) : (
          'Seul un propriétaire de l’espace peut l’allumer.'
        )}
      </Alert>
    )
  }

  const current = currentId ? conversation.data : undefined
  const thinking = current?.status === 'thinking'
  const limitReached = s.used_today >= s.daily_limit

  async function sendText(text: string) {
    const data = await send.mutateAsync({ conversationId: currentId, text })
    setCurrentId(data.id)
  }

  return (
    <section className="ai-panel card-panel" aria-labelledby="ai-title">
      <aside className="ai-side" aria-label="Conversations">
        <button
          type="button"
          className="button button--small"
          onClick={() => {
            setCurrentId(null)
            send.reset()
          }}
        >
          + Nouvelle conversation
        </button>
        {list.isPending && <Skeleton lines={2} />}
        <ul className="ai-side__list">
          {(list.data ?? []).map((c) => (
            <li key={c.id}>
              <button
                type="button"
                className={c.id === currentId ? 'ai-side__item ai-side__item--on' : 'ai-side__item'}
                aria-current={c.id === currentId ? 'true' : undefined}
                onClick={() => setCurrentId(c.id)}
              >
                <span className="ai-side__title">{c.title}</span>
                <span className="ai-side__date">{formatMoment(c.updated_at)}</span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <div className="ai-main">
        <div className="ai-main__head">
          <div>
            <h2 id="ai-title">Assistant IA</h2>
            <p className="card-panel__help">
              Il lit vos projets avec vos droits et prépare les changements. Rien n’est modifié tant
              que vous n’avez pas cliqué sur « Appliquer ».
            </p>
          </div>
          {current && (
            <button
              type="button"
              className="button button--small button--ghost"
              disabled={remove.isPending || thinking}
              onClick={() => remove.mutate(current.id, { onSuccess: () => setCurrentId(null) })}
            >
              Supprimer la conversation
            </button>
          )}
        </div>

        {currentId && conversation.isPending && <Skeleton />}
        {conversation.isError && <Alert>{errorMessage(conversation.error)}</Alert>}
        {current ? (
          <Conversation conversation={current} spaceId={space.id} />
        ) : (
          !currentId && (
            <div className="ai-empty">
              <p>Exemples de demandes :</p>
              <div className="ai-empty__chips">
                {SUGGESTIONS.map((q) => (
                  <button
                    key={q}
                    type="button"
                    className="chip"
                    disabled={send.isPending || limitReached}
                    onClick={() => void sendText(q).catch(() => undefined)}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )
        )}

        {send.isError && <Alert>{errorMessage(send.error)}</Alert>}
        {limitReached && (
          <Alert tone="warn">
            Limite du jour atteinte ({s.daily_limit} questions). Elle repart demain.
          </Alert>
        )}
        <Composer
          disabled={send.isPending || thinking || limitReached}
          pending={send.isPending}
          onSend={sendText}
        />
        <p className="ai-foot muted">
          {s.used_today} / {s.daily_limit} questions aujourd’hui · Vos conversations sont privées.
          L’assistant peut se tromper : relisez chaque proposition.
        </p>
      </div>
    </section>
  )
}

/** Paramètres : allumer ou éteindre l'assistant (propriétaires). */
export function AiSettingsSection({ spaceId }: { spaceId: string }) {
  const status = useAiStatus(spaceId)
  const toggle = useToggleAi(spaceId)
  const s = status.data
  return (
    <section className="card-panel" aria-labelledby="title-ai">
      <div className="card-panel__head">
        <div>
          <h2 id="title-ai">Assistant IA</h2>
          <p className="card-panel__help">
            Dans « Mises à jour », chaque membre peut poser des questions et demander des
            changements. L’assistant agit avec les droits de la personne (un lecteur ne peut rien
            modifier) et chaque changement attend son clic « Appliquer ». Les questions et les
            données consultées sont envoyées à Anthropic (Claude) pour préparer les réponses.
          </p>
        </div>
      </div>
      {status.isPending && <Skeleton lines={1} />}
      {status.isError && <Alert>{errorMessage(status.error)}</Alert>}
      {s && !s.available && (
        <Alert tone="info">
          La clé Anthropic n’est pas encore ajoutée sur le serveur : l’assistant ne peut pas être
          allumé pour l’instant.
        </Alert>
      )}
      {s?.available && (
        <div className="ai-toggle">
          <StatusPill tone={s.enabled ? 'ok' : 'neutral'}>
            {s.enabled ? 'Allumé' : 'Éteint'}
          </StatusPill>
          <button
            type="button"
            className={s.enabled ? 'button button--small' : 'button button--small button--primary'}
            disabled={toggle.isPending}
            onClick={() => toggle.mutate(!s.enabled)}
          >
            {s.enabled ? 'Éteindre l’assistant' : 'Allumer l’assistant'}
          </button>
          <span className="muted">
            Limite : {s.daily_limit} questions par personne et par jour.
          </span>
        </div>
      )}
      {toggle.isError && <Alert>{errorMessage(toggle.error)}</Alert>}
    </section>
  )
}
