import { useState, type InputHTMLAttributes } from 'react'

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'>

/** Champ de mot de passe avec un œil pour afficher ou masquer la saisie. */
export function PasswordInput(props: Props) {
  const [visible, setVisible] = useState(false)
  return (
    <div className="password-input">
      <input {...props} type={visible ? 'text' : 'password'} />
      <button
        type="button"
        className="password-input__toggle"
        aria-label={visible ? 'Masquer le mot de passe' : 'Afficher le mot de passe'}
        aria-pressed={visible}
        aria-controls={props.id}
        onClick={() => setVisible((v) => !v)}
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
          <circle cx="12" cy="12" r="3" />
          {visible && <path d="M3 3l18 18" />}
        </svg>
      </button>
    </div>
  )
}
