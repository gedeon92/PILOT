import { useId } from 'react'

/** Avatar de l'assistant PILOT : une assistante en buste, avec un casque-micro. Sa tête bouge
 * doucement, ses yeux regardent autour d'elle et clignent ; quand elle réfléchit, elle penche
 * la tête, lève les sourcils et regarde en l'air. Tout est dessiné (pas d'image à charger), et
 * les mouvements s'arrêtent si l'utilisateur réduit les animations. */
export function AiAvatar({
  size = 32,
  thinking = false,
  still = false,
}: {
  size?: number
  thinking?: boolean
  /** Immobile (icône du menu) : pas d'animation qui distrait pendant la navigation. */
  still?: boolean
}) {
  const id = useId().replace(/:/g, '')
  const skin = '#9a6340'
  const skinShade = '#7d4c2f'
  const hair = '#231710'
  return (
    <span
      className={['ai-avatar', thinking && 'ai-avatar--thinking', still && 'ai-avatar--still']
        .filter(Boolean)
        .join(' ')}
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <svg viewBox="0 0 120 120" width={size} height={size}>
        <defs>
          <radialGradient id={`${id}-bg`} cx="30%" cy="25%" r="85%">
            <stop offset="0%" stopColor="#ffd6a8" />
            <stop offset="45%" stopColor="#ff8a6b" />
            <stop offset="100%" stopColor="#9b6bff" />
          </radialGradient>
          <linearGradient id={`${id}-top`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#ff6b4a" />
            <stop offset="55%" stopColor="#e8458b" />
            <stop offset="100%" stopColor="#7c5cff" />
          </linearGradient>
          <clipPath id={`${id}-clip`}>
            <circle cx="60" cy="60" r="58" />
          </clipPath>
        </defs>
        <g clipPath={`url(#${id}-clip)`}>
          <circle cx="60" cy="60" r="58" fill={`url(#${id}-bg)`} />
          {/* Buste */}
          <path d="M18 122 C20 98 38 88 60 88 C82 88 100 98 102 122 Z" fill={`url(#${id}-top)`} />
          <path
            d="M50 88 Q60 97 70 88"
            fill="none"
            stroke="#ffffff"
            strokeOpacity="0.55"
            strokeWidth="2.5"
          />
          <rect x="52" y="74" width="16" height="16" rx="6" fill={skinShade} />
          {/* Tête (pivote autour du cou) */}
          <g className="ai-avatar__head">
            <circle cx="40" cy="38" r="13" fill={hair} />
            <circle cx="52" cy="28" r="14" fill={hair} />
            <circle cx="68" cy="28" r="14" fill={hair} />
            <circle cx="80" cy="38" r="13" fill={hair} />
            <circle cx="60" cy="24" r="13" fill={hair} />
            <ellipse cx="37.5" cy="58" rx="4.5" ry="6" fill={skinShade} />
            <ellipse cx="82.5" cy="58" rx="4.5" ry="6" fill={skinShade} />
            <ellipse cx="60" cy="57" rx="22" ry="25" fill={skin} />
            <path d="M39 46 C44 33 76 33 81 46 C74 40 46 40 39 46 Z" fill={hair} />
            {/* Sourcils */}
            <g className="ai-avatar__brows">
              <path
                d="M45.5 47.5 Q50.5 45 55 47"
                fill="none"
                stroke={hair}
                strokeWidth="2.4"
                strokeLinecap="round"
              />
              <path
                d="M65 47 Q69.5 45 74.5 47.5"
                fill="none"
                stroke={hair}
                strokeWidth="2.4"
                strokeLinecap="round"
              />
            </g>
            {/* Yeux */}
            <g className="ai-avatar__eyes">
              <ellipse cx="50.5" cy="55.5" rx="5" ry="4.2" fill="#ffffff" />
              <ellipse cx="69.5" cy="55.5" rx="5" ry="4.2" fill="#ffffff" />
              <g className="ai-avatar__pupils">
                <circle cx="50.5" cy="55.8" r="2.6" fill="#2a1a12" />
                <circle cx="69.5" cy="55.8" r="2.6" fill="#2a1a12" />
                <circle cx="51.4" cy="54.8" r="0.9" fill="#ffffff" />
                <circle cx="70.4" cy="54.8" r="0.9" fill="#ffffff" />
              </g>
            </g>
            <path
              d="M58.5 59 Q60 64.5 62.5 62.5"
              fill="none"
              stroke={skinShade}
              strokeWidth="1.8"
              strokeLinecap="round"
            />
            <circle cx="45" cy="64" r="3.4" fill="#ff7a6b" opacity="0.35" />
            <circle cx="75" cy="64" r="3.4" fill="#ff7a6b" opacity="0.35" />
            <path
              className="ai-avatar__mouth"
              d="M52.5 68 Q60 74.5 67.5 68"
              fill="#ffffff"
              stroke="#5a2a1a"
              strokeWidth="1.6"
              strokeLinejoin="round"
            />
            {/* Casque-micro */}
            <path
              d="M36 54 C34 22 86 22 84 54"
              fill="none"
              stroke="#2c2340"
              strokeWidth="4"
              strokeLinecap="round"
            />
            <rect x="31" y="50" width="9" height="15" rx="4" fill="#2c2340" />
            <rect x="80" y="50" width="9" height="15" rx="4" fill="#2c2340" />
            <path
              d="M35 64 C36 74 44 76 52 74.5"
              fill="none"
              stroke="#2c2340"
              strokeWidth="2.4"
              strokeLinecap="round"
            />
            <circle className="ai-avatar__mic" cx="53.5" cy="74.3" r="3" fill="#ff8a3d" />
          </g>
        </g>
        <circle
          cx="60"
          cy="60"
          r="58"
          fill="none"
          stroke="#ffffff"
          strokeOpacity="0.5"
          strokeWidth="2"
        />
      </svg>
    </span>
  )
}
