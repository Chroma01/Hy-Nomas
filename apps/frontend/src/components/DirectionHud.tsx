import { Eye, EyeOff, Navigation } from 'lucide-react'

interface DirectionHudProps {
  direction: string
  turnNumber: number
  progressPercent: number
  active: boolean
  visible: boolean
  onVisibilityToggle: () => void
}

export function DirectionHud({
  direction,
  turnNumber,
  progressPercent,
  active,
  visible,
  onVisibilityToggle,
}: DirectionHudProps) {
  const progress = Math.max(0, Math.min(100, progressPercent))

  if (!visible) {
    return (
      <button
        className="direction-hud-reveal"
        type="button"
        aria-label="Show real user prompt"
        title="Show real user prompt"
        onClick={onVisibilityToggle}
      >
        <Eye size={17} strokeWidth={1.8} />
        <span>Show prompt</span>
      </button>
    )
  }

  return (
    <aside className="direction-hud" aria-label="Real user prompt">
      <svg
        className="direction-hud-frame"
        viewBox="0 0 360 154"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <defs>
          <linearGradient
            id="direction-hud-surface"
            x1="0"
            y1="0"
            x2="1"
            y2="1"
          >
            <stop
              className="direction-hud-stop-start"
              offset="0"
              stopOpacity="0.97"
            />
            <stop
              className="direction-hud-stop-end"
              offset="1"
              stopOpacity="0.94"
            />
          </linearGradient>
          <filter
            id="direction-hud-shadow"
            x="-20%"
            y="-30%"
            width="140%"
            height="170%"
          >
            <feDropShadow
              dx="0"
              dy="9"
              stdDeviation="12"
              floodColor="#181712"
              floodOpacity="0.28"
            />
          </filter>
        </defs>
        <path
          className="direction-hud-panel"
          d="M18 1H342C351.4 1 359 8.6 359 18V136C359 145.4 351.4 153 342 153H18C8.6 153 1 145.4 1 136V18C1 8.6 8.6 1 18 1Z"
          fill="url(#direction-hud-surface)"
          filter="url(#direction-hud-shadow)"
        />
        <path
          className="direction-hud-rule"
          d="M18 43.5H342"
          vectorEffect="non-scaling-stroke"
        />
        <path
          className="direction-hud-corner"
          d="M1 29V18C1 8.6 8.6 1 18 1H34"
          vectorEffect="non-scaling-stroke"
        />
        <path
          className="direction-hud-corner"
          d="M326 153H342C351.4 153 359 145.4 359 136V125"
          vectorEffect="non-scaling-stroke"
        />
        <rect
          className="direction-hud-track"
          x="18"
          y="140"
          width="324"
          height="3"
          rx="1.5"
        />
        <rect
          className="direction-hud-progress"
          x="18"
          y="140"
          width={324 * progress / 100}
          height="3"
          rx="1.5"
        />
      </svg>

      <div className="direction-hud-content">
        <header>
          <span className="direction-hud-title">
            <span className="direction-hud-icon">
              <Navigation size={13} strokeWidth={1.8} />
            </span>
            <span>
              <small>REAL USER PROMPT</small>
              <strong>Turn {String(turnNumber).padStart(2, '0')}</strong>
            </span>
          </span>
          <span className="direction-hud-tools">
            <span
              className={
                active
                  ? 'direction-hud-state active'
                  : 'direction-hud-state'
              }
            >
              {active ? 'LIVE' : 'PLAYBACK'}
            </span>
            <button
              type="button"
              aria-label="Hide real user prompt"
              title="Hide real user prompt"
              onClick={onVisibilityToggle}
            >
              <EyeOff size={15} strokeWidth={1.8} />
            </button>
          </span>
        </header>
        <p>{direction}</p>
      </div>
    </aside>
  )
}
