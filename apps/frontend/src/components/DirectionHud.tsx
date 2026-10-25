import { Eye, EyeOff } from 'lucide-react'

interface DirectionHudProps {
  direction: string
  visible: boolean
  onVisibilityToggle: () => void
}

export function DirectionHud({
  direction,
  visible,
  onVisibilityToggle,
}: DirectionHudProps) {
  if (!visible) {
    return (
      <button
        className="demo-overlay-toggle demo-overlay-reveal"
        type="button"
        aria-label="Show real user prompt"
        onClick={onVisibilityToggle}
      >
        <Eye size={17} />
        <span>Show prompt</span>
      </button>
    )
  }

  return (
    <aside className="demo-prompt-overlay" aria-label="Real user prompt">
      <span className="demo-text-badge">TEXT</span>
      <p>{direction}</p>
      <button
        className="demo-overlay-toggle"
        type="button"
        aria-label="Hide real user prompt"
        onClick={onVisibilityToggle}
      >
        <EyeOff size={15} />
      </button>
    </aside>
  )
}
