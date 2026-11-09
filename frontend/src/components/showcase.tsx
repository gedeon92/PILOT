/** Présentation animée de PILOT sur les pages de connexion et d'inscription : une petite
 * équipe dessinée fait avancer ses projets (carte déplacée vers « Terminé »), coche ses tâches
 * et prépare un événement dans le calendrier. Les animations sont en CSS (voir app.css,
 * « Vitrine ») et s'arrêtent si l'utilisateur réduit les animations. */

type Hair = 'afro' | 'bun' | 'short'
type Point = [number, number]

/** Bras en deux parties (épaule → coude → main), manche de la couleur du haut. Les classes
 * d'animation (lever, écrire, faire signe) s'appliquent au groupe entier. */
function Arm({
  shoulder,
  elbow,
  hand,
  sleeve,
  skin,
  className,
}: {
  shoulder: Point
  elbow: Point
  hand: Point
  sleeve: string
  skin: string
  className?: string
}) {
  return (
    <g className={className}>
      <path
        d={`M${shoulder[0]} ${shoulder[1]} L${elbow[0]} ${elbow[1]} L${hand[0]} ${hand[1]}`}
        fill="none"
        stroke={sleeve}
        strokeWidth="6.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d={`M${shoulder[0]} ${shoulder[1]} L${elbow[0]} ${elbow[1]} L${hand[0]} ${hand[1]}`}
        fill="none"
        stroke="url(#sc-sleeve-shade)"
        strokeWidth="6.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={hand[0]} cy={hand[1]} r="2.9" fill={skin} />
    </g>
  )
}

/** Personnage aux proportions réelles (environ 7 têtes de haut), dessiné pieds au sol en
 * (0, 0) : jambes, chaussures, haut, cou, tête avec oreilles, coiffure et visage. */
function Person({
  x,
  skin,
  top,
  pants,
  shoes,
  hair,
  hairStyle,
  blazer,
  className,
  children,
}: {
  x: number
  skin: string
  top: string
  pants: string
  shoes: string
  hair: string
  hairStyle: Hair
  /** Veste ouverte sur le haut (couleur de la veste). */
  blazer?: string
  className: string
  children?: React.ReactNode
}) {
  const jacket = blazer ?? top
  return (
    <g className={`sc-person ${className}`} transform={`translate(${x} 390)`}>
      <g className="sc-person__body">
        <ellipse className="sc-shadow" cx="0" cy="1.5" rx="22" ry="4" />
        {/* Jambes (pantalon) et chaussures */}
        <g className="sc-leg sc-leg--l">
          <path d="M-11.5 -66 L-0.8 -66 L-2.2 -7 L-9.8 -7 Z" fill={pants} stroke="none" />
          <path d="M-11.5 -66 L-6 -66 L-7.2 -7 L-9.8 -7 Z" fill="#000" opacity="0.18" />
          <path d="M-11.6 -7.5 h10.2 q3.6 0 4 4 v3.5 h-14.6 z" fill={shoes} stroke="none" />
        </g>
        <g className="sc-leg sc-leg--r">
          <path d="M0.8 -66 L11.5 -66 L9.8 -7 L2.2 -7 Z" fill={pants} stroke="none" />
          <path d="M6 -66 L11.5 -66 L9.8 -7 L7.2 -7 Z" fill="#000" opacity="0.12" />
          <path d="M1.4 -7.5 h10.2 q3.6 0 4 4 v3.5 h-14.6 z" fill={shoes} stroke="none" />
        </g>
        {/* Cou */}
        <rect x="-3.2" y="-121" width="6.4" height="10" rx="2" fill={skin} />
        <rect x="-3.2" y="-115" width="6.4" height="4" fill="#000" opacity="0.18" />
        {/* Haut : épaules, taille, ceinture */}
        <path
          d="M-15 -104 Q-15 -111 -9 -112.5 L-3.6 -113.5 L0 -106 L3.6 -113.5 L9 -112.5 Q15 -111 15 -104 L12.5 -70 Q12 -66 8 -66 L-8 -66 Q-12 -66 -12.5 -70 Z"
          fill={top}
        />
        {blazer && (
          <>
            <path
              d="M-15 -104 Q-15 -111 -9 -112.5 L-3.6 -113.5 L-1.2 -96 L-4 -66 L-8 -66 Q-12 -66 -12.5 -70 Z"
              fill={jacket}
            />
            <path
              d="M15 -104 Q15 -111 9 -112.5 L3.6 -113.5 L1.2 -96 L4 -66 L8 -66 Q12 -66 12.5 -70 Z"
              fill={jacket}
            />
          </>
        )}
        <path
          d="M-15 -104 Q-15 -111 -9 -112.5 L-3.6 -113.5 L0 -106 L3.6 -113.5 L9 -112.5 Q15 -111 15 -104 L12.5 -70 Q12 -66 8 -66 L-8 -66 Q-12 -66 -12.5 -70 Z"
          fill="url(#sc-body-shade)"
        />
        <rect x="-12" y="-69.5" width="24" height="3" rx="1" fill="#000" opacity="0.28" />
        {/* Tête */}
        <g className="sc-head">
          {hairStyle === 'afro' && <circle cx="0" cy="-130" r="12.5" fill={hair} />}
          {hairStyle === 'bun' && <circle cx="0" cy="-141" r="4.8" fill={hair} />}
          <ellipse cx="-8.2" cy="-126" rx="1.7" ry="2.6" fill={skin} />
          <ellipse cx="8.2" cy="-126" rx="1.7" ry="2.6" fill={skin} />
          <ellipse cx="0" cy="-126.5" rx="8" ry="9.6" fill={skin} />
          <ellipse cx="0" cy="-126.5" rx="8" ry="9.6" fill="url(#sc-face-shade)" />
          {hairStyle !== 'afro' && (
            <path
              d={
                hairStyle === 'bun'
                  ? 'M-8.4 -127 Q-9.4 -137.5 0 -138 Q9.4 -137.5 8.4 -127 Q7 -132.5 0 -133.2 Q-7 -132.5 -8.4 -127 Z'
                  : 'M-8.5 -126 Q-9.6 -138 0.5 -138.2 Q9.6 -137.4 8.5 -126 Q7.6 -131.6 2 -132.6 Q-5.6 -133.4 -8.5 -126 Z'
              }
              fill={hair}
            />
          )}
          {hairStyle === 'afro' && (
            <path
              d="M-8.6 -127 Q-8 -135.5 0 -135.8 Q8 -135.5 8.6 -127 Q6.5 -131.8 0 -132 Q-6.5 -131.8 -8.6 -127 Z"
              fill={hair}
            />
          )}
          {/* Visage : sourcils, yeux, nez, bouche */}
          <path
            d="M-5.3 -130.3 q2 -1 3.6 0"
            stroke={hair}
            strokeWidth="1"
            fill="none"
            strokeLinecap="round"
          />
          <path
            d="M1.7 -130.3 q2 -1 3.6 0"
            stroke={hair}
            strokeWidth="1"
            fill="none"
            strokeLinecap="round"
          />
          <ellipse cx="-3.3" cy="-127.4" rx="1.05" ry="1.3" className="sc-eye" />
          <ellipse cx="3.3" cy="-127.4" rx="1.05" ry="1.3" className="sc-eye" />
          <path
            d="M0.2 -126 q1 2.6 -0.9 3.1"
            stroke="#000"
            strokeOpacity="0.3"
            strokeWidth="0.9"
            fill="none"
            strokeLinecap="round"
          />
          <path d="M-2.6 -120.6 q2.6 1.9 5.2 0" className="sc-smile" />
          <circle cx="-5" cy="-122.6" r="1.7" className="sc-cheek" />
          <circle cx="5" cy="-122.6" r="1.7" className="sc-cheek" />
        </g>
        {children}
      </g>
    </g>
  )
}

function Sparkle({
  x,
  y,
  size = 1,
  delay = 0,
}: {
  x: number
  y: number
  size?: number
  delay?: number
}) {
  return (
    <path
      className="sc-sparkle"
      style={{ animationDelay: `${delay}s` }}
      transform={`translate(${x} ${y}) scale(${size})`}
      d="M0-7C1-2 2-1 7 0 2 1 1 2 0 7-1 2-2 1-7 0-2-1-1-2 0-7z"
    />
  )
}

function Card({
  x,
  y,
  color,
  w1 = 58,
  w2 = 40,
}: {
  x: number
  y: number
  color: string
  w1?: number
  w2?: number
}) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect className="sc-card" width="92" height="38" rx="8" />
      <rect x="0" y="0" width="4" height="38" rx="2" fill={color} />
      <rect className="sc-text" x="12" y="10" width={w1} height="6" rx="3" />
      <rect className="sc-text sc-text--soft" x="12" y="22" width={w2} height="5" rx="2.5" />
    </g>
  )
}

function Scene() {
  const days = Array.from({ length: 21 }, (_, i) => i)
  return (
    <svg
      className="showcase__scene"
      viewBox="0 0 560 336"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Illustration animée : une équipe fait passer un projet à « Terminé », coche ses tâches et prépare un événement dans le calendrier."
    >
      <defs>
        {/* Ombres douces des personnages : bords plus sombres, lumière venant de la gauche. */}
        <linearGradient id="sc-body-shade" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor="#fff" stopOpacity="0.16" />
          <stop offset="0.45" stopColor="#fff" stopOpacity="0" />
          <stop offset="1" stopColor="#000" stopOpacity="0.28" />
        </linearGradient>
        <linearGradient id="sc-sleeve-shade" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#fff" stopOpacity="0.12" />
          <stop offset="1" stopColor="#000" stopOpacity="0.22" />
        </linearGradient>
        <radialGradient id="sc-face-shade" cx="38%" cy="36%" r="70%">
          <stop offset="0" stopColor="#fff" stopOpacity="0.2" />
          <stop offset="0.6" stopColor="#fff" stopOpacity="0" />
          <stop offset="1" stopColor="#000" stopOpacity="0.22" />
        </radialGradient>
        <radialGradient id="sc-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#ff7a1a" stopOpacity="0.35" />
          <stop offset="55%" stopColor="#8b5cf6" stopOpacity="0.14" />
          <stop offset="100%" stopColor="#8b5cf6" stopOpacity="0" />
        </radialGradient>
      </defs>
      <ellipse className="sc-glow" cx="280" cy="300" rx="280" ry="70" fill="url(#sc-glow)" />

      {/* Tableau des projets */}
      <g>
        <rect className="sc-panel" x="16" y="16" width="338" height="158" rx="16" />
        {[
          ['#ff7a1a', 0],
          ['#8b5cf6', 1],
          ['#22d3ee', 2],
        ].map(([color, i]) => (
          <circle
            key={String(color)}
            cx={300 + Number(i) * 13}
            cy="36"
            r="8"
            fill={String(color)}
            className="sc-team"
          />
        ))}
        <circle cx="34" cy="36" r="4" fill="#ff7a1a" />
        <text className="sc-title" x="46" y="40">
          Projets
        </text>
        {[
          ['À faire', 28],
          ['En cours', 138],
          ['Terminé', 248],
        ].map(([label, x]) => (
          <text key={label} className="sc-label" x={Number(x) + 2} y="66">
            {label}
          </text>
        ))}
        <Card x={28} y={76} color="#8b5cf6" />
        <Card x={28} y={122} color="#22d3ee" w1={46} w2={52} />
        <g>
          <Card x={138} y={76} color="#ff3d81" w1={50} />
          <rect className="sc-track" x="150" y="104" width="70" height="4" rx="2" />
          <rect className="sc-grow" x="150" y="104" width="70" height="4" rx="2" />
        </g>
        <Card x={248} y={76} color="#22c55e" w1={44} />
        <circle cx="328" cy="86" r="7" fill="#22c55e" />
        <path d="M324.5 86l2.5 2.5 4.5-5" className="sc-tick-mark" />
        {/* Carte qui passe de « En cours » à « Terminé » */}
        <g className="sc-moving">
          <Card x={138} y={124} color="#ff7a1a" w1={60} w2={34} />
          <g className="sc-moving__done">
            <circle cx="218" cy="134" r="7" fill="#22c55e" />
            <path d="M214.5 134l2.5 2.5 4.5-5" className="sc-tick-mark" />
          </g>
        </g>
      </g>

      {/* Calendrier des événements */}
      <g>
        <rect className="sc-panel" x="370" y="16" width="174" height="160" rx="16" />
        <text className="sc-title" x="386" y="40">
          Novembre
        </text>
        {days.map((i) => {
          const cx = 388 + (i % 7) * 22
          const cy = 58 + Math.floor(i / 7) * 24
          const event = i === 11
          return (
            <rect
              key={i}
              className={event ? 'sc-day sc-day--event' : 'sc-day'}
              x={cx}
              y={cy}
              width="16"
              height="16"
              rx="4"
            />
          )
        })}
        <g className="sc-bubble">
          <rect x="398" y="134" width="132" height="30" rx="10" className="sc-bubble__box" />
          <text className="sc-bubble__text" x="410" y="153">
            🎪 Salon · dans 3 jours
          </text>
        </g>
      </g>

      {/* Notification */}
      <g className="sc-toast">
        <rect x="210" y="160" width="132" height="28" rx="10" className="sc-toast__box" />
        <circle cx="225" cy="174" r="6" fill="#22c55e" />
        <path d="M222 174l2 2 4-4" className="sc-tick-mark" />
        <text className="sc-toast__text" x="236" y="178">
          Projet terminé !
        </text>
      </g>

      <Sparkle x={362} y={10} size={0.9} />
      <Sparkle x={548} y={196} size={0.7} delay={1.2} />
      <Sparkle x={24} y={190} size={0.8} delay={2.1} />
      <Sparkle x={250} y={222} size={0.6} delay={0.6} />

      {/* L'équipe, au sol */}
      <g transform="translate(0 -60)">
        <line className="sc-floor" x1="16" y1="390" x2="544" y2="390" />

        {/* Personne 1 : coche sa liste de tâches */}
        <Person
          x={70}
          skin="#8d5524"
          top="#8b5cf6"
          pants="#2b2f45"
          shoes="#14161f"
          hair="#1f1308"
          hairStyle="afro"
          className="sc-p1"
        >
          <Arm
            shoulder={[-13, -107]}
            elbow={[-15, -89]}
            hand={[-3, -82]}
            sleeve="#8b5cf6"
            skin="#8d5524"
          />
          <g className="sc-clipboard">
            <rect x="-4" y="-103" width="23" height="30" rx="2.5" className="sc-clip" />
            <rect x="3.5" y="-105" width="8" height="3.6" rx="1.2" fill="#94a3b8" />
            {[0, 1, 2].map((i) => (
              <g key={i}>
                <rect x="0" y={-97 + i * 8} width="4" height="4" rx="0.8" className="sc-box" />
                <path
                  d={`M0.4 ${-95 + i * 8}l1.3 1.3 2.3-2.6`}
                  className={`sc-check sc-check--${i + 1}`}
                />
                <rect
                  x="6.5"
                  y={-96 + i * 8}
                  width="9.5"
                  height="2.4"
                  rx="1.2"
                  className="sc-text"
                />
              </g>
            ))}
          </g>
          <Arm
            className="sc-arm--write"
            shoulder={[13, -107]}
            elbow={[16, -91]}
            hand={[9, -86]}
            sleeve="#8b5cf6"
            skin="#8d5524"
          />
        </Person>

        {/* Personne 2 : fait avancer le projet (veste ouverte) */}
        <g className="sc-walker">
          <Person
            x={190}
            skin="#6b3e1f"
            top="#f8fafc"
            blazer="#ff7a1a"
            pants="#1f2433"
            shoes="#0d0f15"
            hair="#120a04"
            hairStyle="bun"
            className="sc-p2"
          >
            <Arm
              shoulder={[-13, -107]}
              elbow={[-16, -88]}
              hand={[-15, -71]}
              sleeve="#ff7a1a"
              skin="#6b3e1f"
            />
            <Arm
              className="sc-arm--up"
              shoulder={[13, -107]}
              elbow={[19, -122]}
              hand={[23, -138]}
              sleeve="#ff7a1a"
              skin="#6b3e1f"
            />
          </Person>
        </g>

        {/* Personne 3 : montre l'événement */}
        <Person
          x={470}
          skin="#c68642"
          top="#22d3ee"
          pants="#334155"
          shoes="#1e293b"
          hair="#2b1a0c"
          hairStyle="short"
          className="sc-p3"
        >
          <Arm
            shoulder={[13, -107]}
            elbow={[16, -88]}
            hand={[15, -71]}
            sleeve="#22d3ee"
            skin="#c68642"
          />
          <Arm
            className="sc-arm--wave"
            shoulder={[-13, -107]}
            elbow={[-20, -121]}
            hand={[-23, -137]}
            sleeve="#22d3ee"
            skin="#c68642"
          />
        </Person>
      </g>
    </svg>
  )
}

const STEPS = [
  {
    title: 'Ajoutez vos projets',
    text: 'Responsable, échéance et prochaine étape.',
  },
  {
    title: 'Suivez leur avancement',
    text: 'Tâches, décisions et retards d’un coup d’œil.',
  },
  {
    title: 'Préparez vos événements',
    text: 'Calendrier, timeline et rappels par e-mail.',
  },
]

export function Showcase() {
  return (
    <section className="showcase" aria-labelledby="showcase-title">
      <p className="eyebrow showcase__eyebrow">Projets · Événements · Équipes</p>
      <h2 id="showcase-title" className="showcase__title">
        Vos projets avancent. <span className="showcase__accent">Rien ne vous échappe.</span>
      </h2>
      <p className="showcase__lead">
        Le suivi de vos projets et de vos événements, au même endroit : chacun sait où en est le
        travail, ce qui bloque et ce qui arrive.
      </p>
      <Scene />
      <ol className="showcase__steps">
        {STEPS.map((step, i) => (
          <li key={step.title} className={`showcase__step showcase__step--${i + 1}`}>
            <span className="showcase__num">{i + 1}</span>
            <span>
              <strong>{step.title}</strong>
              <span className="showcase__text">{step.text}</span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  )
}
