import { describe, expect, it } from 'vitest'
import * as THREE from 'three'
import type { CameraFrame } from './types'
import {
  trimTrailingStaticCameraFrames,
} from './cameraTrajectory'

function frame(index: number, yawDegrees: number): CameraFrame {
  const q = new THREE.Quaternion().setFromEuler(
    new THREE.Euler(0, THREE.MathUtils.degToRad(yawDegrees), 0, 'YXZ'),
  )
  return {
    frame: index,
    t: Math.round(index * 1000 / 24),
    position: { x: 1, y: 2, z: 3 },
    quaternion: { x: q.x, y: q.y, z: q.z, w: q.w },
    fov: 55,
  }
}

describe('recorded camera trailing wait removal', () => {
  it('removes only duplicate poses at the end and retains the final pose', () => {
    const frames = [frame(0, 0), frame(1, 10), frame(2, 20), frame(3, 20), frame(4, 20)]
    expect(trimTrailingStaticCameraFrames(frames).map((item) => item.frame))
      .toEqual([0, 1, 2])
  })

  it('ignores FOV-only differences in the trailing stationary suffix', () => {
    const frames = [frame(0, 0), frame(1, 10), frame(2, 10)]
    frames[2].fov = 70
    expect(trimTrailingStaticCameraFrames(frames).map((item) => item.frame))
      .toEqual([0, 1])
  })

  it('preserves a stationary pause in the middle when movement resumes', () => {
    const frames = [
      frame(0, 0), frame(1, 10), frame(2, 10), frame(3, 10),
      frame(4, 20), frame(5, 20), frame(6, 20),
    ]
    expect(trimTrailingStaticCameraFrames(frames).map((item) => item.frame))
      .toEqual([0, 1, 2, 3, 4])
  })

  it('keeps one frame when the entire recording is stationary', () => {
    expect(trimTrailingStaticCameraFrames([frame(0, 0), frame(1, 0), frame(2, 0)]))
      .toHaveLength(1)
  })
})
