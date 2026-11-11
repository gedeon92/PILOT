import { useId } from 'react'

/** Avatar de l'assistant PILOT : une petite bulle lumineuse aux couleurs de PILOT (orange,
 * rose, violet, cyan), avec des yeux qui clignent. Quand l'assistant réfléchit, il « pense » :
 * le halo pulse et les yeux regardent de côté. Animations coupées si l'utilisateur réduit
 * les mouvements. */
export function AiAvatar({ size = 32, thinking = false }: { size?: number; thinking?: boolean }) {
  const id = useId().replace(/:/g, '')
  return (
    <span
      className={thinking ? 'ai-avatar ai-avatar--thinking' : 'ai-avatar'}
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <svg viewBox="0 0 64 64" width={size} height={size}>
        <defs>
          <radialGradient id={`${id}-body`} cx="34%" cy="28%" r="80%">
            <stop offset="0%" stopColor="#ffc078" />
            <stop offset="38%" stopColor="#ff6b4a" />
            <stop offset="70%" stopColor="#e8458b" />
            <stop offset="100%" stopColor="#7c5cff" />
          </radialGradient>
          <linearGradient id={`${id}-ring`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#ffb36b" />
            <stop offset="50%" stopColor="#c45cff" />
            <stop offset="100%" stopColor="#3ee0ff" />
          </linearGradient>
          <radialGradient id={`${id}-shine`} cx="30%" cy="22%" r="40%">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0.75" />
            <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
          </radialGradient>
        </defs>
        <circle
          className="ai-avatar__halo"
          cx="32"
          cy="32"
          r="30"
          fill="none"
          stroke={`url(#${id}-ring)`}
          strokeWidth="2.5"
        />
        <circle cx="32" cy="33" r="25" fill={`url(#${id}-body)`} />
        <circle cx="32" cy="33" r="25" fill={`url(#${id}-shine)`} />
        <g className="ai-avatar__eyes">
          <ellipse cx="24.5" cy="31" rx="3.6" ry="4.6" fill="#ffffff" />
          <ellipse cx="39.5" cy="31" rx="3.6" ry="4.6" fill="#ffffff" />
          <circle className="ai-avatar__pupil" cx="25.3" cy="32" r="1.9" fill="#2a1a4a" />
          <circle className="ai-avatar__pupil" cx="40.3" cy="32" r="1.9" fill="#2a1a4a" />
        </g>
        <path
          d="M25.5 41.5 Q32 46.5 38.5 41.5"
          fill="none"
          stroke="#ffffff"
          strokeWidth="2.6"
          strokeLinecap="round"
        />
        <path
          className="ai-avatar__spark"
          d="M52 6 L53.6 10.4 L58 12 L53.6 13.6 L52 18 L50.4 13.6 L46 12 L50.4 10.4 Z"
          fill="#3ee0ff"
        />
      </svg>
    </span>
  )
}
