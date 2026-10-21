import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DirectionHud } from './DirectionHud'

afterEach(cleanup)

describe('DirectionHud', () => {
  it('renders the real user prompt in a vector-backed playback panel', () => {
    const onVisibilityToggle = vi.fn()
    const { container } = render(
      <DirectionHud
        direction="Follow the river toward the bridge"
        turnNumber={2}
        progressPercent={42}
        active
        visible
        onVisibilityToggle={onVisibilityToggle}
      />,
    )

    expect(screen.getByLabelText('Real user prompt')).toHaveTextContent(
      'Follow the river toward the bridge',
    )
    expect(screen.getByText('REAL USER PROMPT')).toBeInTheDocument()
    expect(screen.getByText('Turn 02')).toBeInTheDocument()
    expect(screen.getByText('LIVE')).toBeInTheDocument()
    expect(container.querySelector('.direction-hud-frame')).toBeInstanceOf(
      SVGSVGElement,
    )
    expect(container.querySelector('.direction-hud-progress')).toHaveAttribute(
      'width',
      '136.08',
    )
  })

  it('offers compact controls to hide and restore the prompt', async () => {
    const user = userEvent.setup()
    const onVisibilityToggle = vi.fn()
    const { rerender } = render(
      <DirectionHud
        direction="Follow the river toward the bridge"
        turnNumber={2}
        progressPercent={42}
        active
        visible
        onVisibilityToggle={onVisibilityToggle}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Hide real user prompt' }))
    expect(onVisibilityToggle).toHaveBeenCalledOnce()

    rerender(
      <DirectionHud
        direction="Follow the river toward the bridge"
        turnNumber={2}
        progressPercent={42}
        active
        visible={false}
        onVisibilityToggle={onVisibilityToggle}
      />,
    )
    expect(screen.queryByLabelText('Real user prompt')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Show real user prompt' }))
    expect(onVisibilityToggle).toHaveBeenCalledTimes(2)
  })
})
