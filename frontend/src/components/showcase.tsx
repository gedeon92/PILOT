/** Présentation animée de PILOT sur les pages de connexion et d'inscription : une petite
 * équipe dessinée fait avancer ses projets (carte déplacée vers « Terminé »), coche ses tâches
 * et prépare un événement dans le calendrier. Les animations sont en CSS (voir app.css,
 * « Vitrine ») et s'arrêtent si l'utilisateur réduit les animations. */

function Person({
  x,
  skin,
  shirt,
  hair,
  className,
  children,
}: {
  x: number
  skin: string
  shirt: string
  hair: string
  className: string
  children?: React.ReactNode
}) {
  // Pieds au sol (y = 385), tête vers y = 283.
  return (
    <g className={`sc-person ${className}`} transform={`translate(${x} 0)`}>
      <g className="sc-person__body" style={{ color: skin }}>
        <ellipse className="sc-shadow" cx="0" cy="388" rx="24" ry="5" />
        <line className="sc-leg sc-leg--l" x1="-7" y1="343" x2="-7" y2="384" />
        <line className="sc-leg sc-leg--r" x1="7" y1="343" x2="7" y2="384" />
        <rect x="-17" y="300" width="34" height="48" rx="13" fill={shirt} />
        <g className="sc-head">
          <circle cx="0" cy="284" r="14" fill={skin} />
          <path d={`M-14 282a14 14 0 0 1 28 0c-6-6-20-6-28 0z`} fill={hair} />
          <circle cx="-5" cy="286" r="1.6" className="sc-eye" />
          <circle cx="5" cy="286" r="1.6" className="sc-eye" />
          <path d="M-4 291q4 3 8 0" className="sc-smile" />
        </g>
        {children}
      </g>
    </g>
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
      viewBox="0 0 560 400"
      role="img"
      aria-label="Illustration animée : une équipe fait passer un projet à « Terminé », coche ses tâches et prépare un événement dans le calendrier."
    >
      {/* Tableau des projets */}
      <g>
        <rect className="sc-panel" x="16" y="16" width="338" height="186" rx="16" />
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

      {/* Avancement global */}
      <g>
        <rect className="sc-panel" x="370" y="188" width="174" height="74" rx="14" />
        <text className="sc-label" x="384" y="208">
          Avancement
        </text>
        <rect className="sc-track" x="384" y="220" width="146" height="8" rx="4" />
        <rect className="sc-grow sc-grow--slow" x="384" y="220" width="146" height="8" rx="4" />
        <rect className="sc-track" x="384" y="238" width="146" height="8" rx="4" />
        <rect className="sc-grow sc-grow--late" x="384" y="238" width="104" height="8" rx="4" />
      </g>

      {/* Notification */}
      <g className="sc-toast">
        <rect x="150" y="214" width="150" height="30" rx="10" className="sc-toast__box" />
        <circle cx="166" cy="229" r="6" fill="#22c55e" />
        <path d="M163 229l2 2 4-4" className="sc-tick-mark" />
        <text className="sc-toast__text" x="178" y="233">
          Projet terminé !
        </text>
      </g>

      {/* Sol */}
      <line className="sc-floor" x1="16" y1="390" x2="544" y2="390" />

      {/* Personne 1 : coche sa liste de tâches */}
      <Person x={70} skin="#8d5524" shirt="#8b5cf6" hair="#1f1308" className="sc-p1">
        <line className="sc-arm" x1="-12" y1="308" x2="10" y2="326" />
        <g className="sc-clipboard">
          <rect x="6" y="306" width="30" height="38" rx="4" className="sc-clip" />
          {[0, 1, 2].map((i) => (
            <g key={i}>
              <rect x="11" y={314 + i * 10} width="5" height="5" rx="1" className="sc-box" />
              <path
                d={`M11.5 ${316.5 + i * 10}l1.6 1.6 2.8-3`}
                className={`sc-check sc-check--${i + 1}`}
              />
              <rect x="19" y={315 + i * 10} width="12" height="3" rx="1.5" className="sc-text" />
            </g>
          ))}
        </g>
        <line className="sc-arm sc-arm--write" x1="12" y1="308" x2="22" y2="322" />
      </Person>

      {/* Personne 2 : fait avancer le projet */}
      <g className="sc-walker">
        <Person x={190} skin="#6b3e1f" shirt="#ff7a1a" hair="#120a04" className="sc-p2">
          <line className="sc-arm" x1="-12" y1="308" x2="-20" y2="336" />
          <line className="sc-arm sc-arm--up" x1="12" y1="306" x2="28" y2="276" />
        </Person>
      </g>

      {/* Personne 3 : montre l'événement */}
      <Person x={470} skin="#c68642" shirt="#22d3ee" hair="#2b1a0c" className="sc-p3">
        <line className="sc-arm" x1="12" y1="308" x2="20" y2="336" />
        <line className="sc-arm sc-arm--wave" x1="-12" y1="306" x2="-30" y2="278" />
      </Person>
    </svg>
  )
}

const STEPS = [
  {
    title: 'Ajoutez vos projets',
    text: 'Responsable, échéance, prochaine étape : tout au même endroit.',
  },
  {
    title: 'Suivez leur avancement',
    text: 'Tâches, décisions attendues et retards visibles d’un coup d’œil.',
  },
  {
    title: 'Préparez vos événements',
    text: 'Calendrier, timeline et rappels par e-mail avant chaque échéance.',
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
        PILOT réunit le suivi de vos projets et de vos événements : chacun sait où en est le
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
