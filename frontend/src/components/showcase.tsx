/** Présentation animée de PILOT sur les pages de connexion et d'inscription : une petite
 * équipe (avatars 3D) fait avancer ses projets (carte déplacée vers « Terminé »), coche ses
 * tâches et prépare un événement dans le calendrier. Les animations sont en CSS (voir app.css,
 * « Vitrine ») et s'arrêtent si l'utilisateur réduit les animations. */

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

      {/* L'équipe : avatars 3D découpés en morceaux (marionnettes) : tête, bras, mains et
          liste bougent chacun autour de leur articulation (voir app.css, « Marionnettes »). */}
      <g className="sc-avatar sc-avatar--1">
        <svg x="30" y="182" width="77" height="154" viewBox="0 0 260 520">
          <image href="/showcase/avatar-1-base.webp" width="260" height="520" />
          <image
            className="sc-p1-head"
            href="/showcase/avatar-1-head.webp"
            width="260"
            height="520"
          />
          <image
            className="sc-p1-hands"
            href="/showcase/avatar-1-hands.webp"
            width="260"
            height="520"
          />
        </svg>
      </g>
      <g className="sc-walker">
        <g className="sc-avatar sc-avatar--2">
          <svg x="140" y="186" width="94" height="150" viewBox="0 0 317 503">
            <image href="/showcase/avatar-2-base.webp" width="317" height="503" />
            <image
              className="sc-p2-head"
              href="/showcase/avatar-2-head.webp"
              width="317"
              height="503"
            />
            <g className="sc-p2-arm">
              <image href="/showcase/avatar-2-arm.webp" width="317" height="503" />
              <image
                className="sc-p2-hand"
                href="/showcase/avatar-2-hand.webp"
                width="317"
                height="503"
              />
            </g>
          </svg>
        </g>
      </g>
      <g className="sc-avatar sc-avatar--3">
        <svg x="410" y="190" width="96" height="146" viewBox="0 0 318 480">
          <image href="/showcase/avatar-3-base.webp" width="318" height="480" />
          <image
            className="sc-p3-head"
            href="/showcase/avatar-3-head.webp"
            width="318"
            height="480"
          />
          <image
            className="sc-p3-hand"
            href="/showcase/avatar-3-hand.webp"
            width="318"
            height="480"
          />
        </svg>
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
