import { Eye, EyeOff, Navigation } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type RefObject } from 'react'
import * as THREE from 'three'
import type { CameraFrame, CameraKeyEvent, CameraPath } from '../types'

interface CameraPlaybackOverlayProps {
  path: CameraPath
  videoRef: RefObject<HTMLVideoElement | null>
  turnNumber: number
  segmentStartSeconds: number
  segmentDurationSeconds: number
  theme: 'dark' | 'light'
  visible: boolean
  onVisibilityToggle: () => void
}

interface CameraActions {
  forward: boolean
  backward: boolean
  left: boolean
  right: boolean
  lookUp: boolean
  lookDown: boolean
  lookLeft: boolean
  lookRight: boolean
}

const IDLE_ACTIONS: CameraActions = {
  forward: false,
  backward: false,
  left: false,
  right: false,
  lookUp: false,
  lookDown: false,
  lookLeft: false,
  lookRight: false,
}

function frameAtTime(frames: CameraFrame[], milliseconds: number) {
  if (frames.length <= 1) {
    return { index: 0, position: frames[0]?.position, quaternion: frames[0]?.quaternion }
  }
  let right = frames.findIndex((frame) => frame.t >= milliseconds)
  if (right < 0) right = frames.length - 1
  const left = Math.max(0, right - 1)
  const a = frames[left]
  const b = frames[right]
  const span = Math.max(1, b.t - a.t)
  const alpha = Math.min(1, Math.max(0, (milliseconds - a.t) / span))
  const position = new THREE.Vector3(
    a.position.x,
    a.position.y,
    a.position.z,
  ).lerp(new THREE.Vector3(b.position.x, b.position.y, b.position.z), alpha)
  const quaternion = new THREE.Quaternion(
    a.quaternion.x,
    a.quaternion.y,
    a.quaternion.z,
    a.quaternion.w,
  ).slerp(
    new THREE.Quaternion(
      b.quaternion.x,
      b.quaternion.y,
      b.quaternion.z,
      b.quaternion.w,
    ),
    alpha,
  )
  return { index: right, position, quaternion }
}

export function actionsAtTime(
  events: CameraKeyEvent[],
  milliseconds: number,
): CameraActions {
  const actions = { ...IDLE_ACTIONS }
  const actionByCode = {
    KeyW: 'forward',
    KeyA: 'left',
    KeyS: 'backward',
    KeyD: 'right',
    ArrowUp: 'lookUp',
    ArrowDown: 'lookDown',
    ArrowLeft: 'lookLeft',
    ArrowRight: 'lookRight',
  } as const
  for (const event of events) {
    if (event.t > milliseconds) break
    actions[actionByCode[event.code]] = event.pressed
  }
  return actions
}

export function cameraSegmentIsActive(
  localSeconds: number,
  segmentDurationSeconds: number,
) {
  return (
    localSeconds >= 0
    && localSeconds < Math.max(0, segmentDurationSeconds)
  )
}

function Key({
  label,
  active,
}: {
  label: string
  active: boolean
}) {
  return <kbd className={active ? 'active' : ''}>{label}</kbd>
}

export function CameraPlaybackOverlay({
  path,
  videoRef,
  turnNumber,
  segmentStartSeconds,
  segmentDurationSeconds,
  theme,
  visible,
  onVisibilityToggle,
}: CameraPlaybackOverlayProps) {
  const mountRef = useRef<HTMLDivElement>(null)
  const markerRef = useRef<THREE.Group | null>(null)
  const [actions, setActions] = useState<CameraActions>(IDLE_ACTIONS)
  const [progressPercent, setProgressPercent] = useState(0)
  const [isActive, setIsActive] = useState(false)
  const frames = useMemo(() => path.frames ?? [], [path.frames])
  const keyEvents = useMemo(() => path.keyEvents ?? [], [path.keyEvents])

  useEffect(() => {
    const mount = mountRef.current
    if (!visible || !mount || frames.length === 0) return

    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    } catch {
      return
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    const lightTheme = theme === 'light'
    const palette = lightTheme
      ? {
          background: 0xeee8dc,
          hemisphereSky: 0xfffcf5,
          hemisphereGround: 0x9c927f,
          gridMajor: 0x607b45,
          gridMinor: 0xc7beae,
          path: 0x8c967d,
          travelled: 0x526e39,
          start: 0x3f3b34,
          end: 0x607b45,
          marker: 0x25241f,
        }
      : {
          background: 0x090b10,
          hemisphereSky: 0xffffff,
          hemisphereGround: 0x283044,
          gridMajor: 0x4e5850,
          gridMinor: 0x242a2b,
          path: 0x77806d,
          travelled: 0xc8f259,
          start: 0xffffff,
          end: 0xc8f259,
          marker: 0xffffff,
        }
    renderer.setClearColor(palette.background, lightTheme ? 0.96 : 0.88)
    mount.append(renderer.domElement)

    const scene = new THREE.Scene()
    const previewCamera = new THREE.PerspectiveCamera(38, 1, 0.01, 10000)
    const positions = frames.map(
      (frame) => new THREE.Vector3(frame.position.x, frame.position.y, frame.position.z),
    )
    const bounds = new THREE.Box3().setFromPoints(positions)
    const center = bounds.getCenter(new THREE.Vector3())
    const boundsSize = bounds.getSize(new THREE.Vector3())
    const size = Math.max(boundsSize.x, boundsSize.z, 1)
    // Keep the preview camera centered on the trajectory's X axis. The
    // elevated perspective preserves depth while avoiding the sideways skew
    // caused by viewing from an offset X position.
    previewCamera.position.set(
      center.x,
      center.y + Math.max(size * 0.9, 2.4),
      center.z + Math.max(size * 1.45, 3.8),
    )
    previewCamera.lookAt(center)

    scene.add(
      new THREE.HemisphereLight(
        palette.hemisphereSky,
        palette.hemisphereGround,
        lightTheme ? 2.3 : 2,
      ),
    )
    const grid = new THREE.GridHelper(
      size * 2.2,
      8,
      palette.gridMajor,
      palette.gridMinor,
    )
    grid.position.y = bounds.min.y - size * 0.08
    const gridMaterials = Array.isArray(grid.material) ? grid.material : [grid.material]
    gridMaterials.forEach((material) => {
      material.transparent = true
      material.opacity = 0.42
    })
    scene.add(grid)

    const pathGeometry = new THREE.BufferGeometry().setFromPoints(positions)
    const pathLine = new THREE.Line(
      pathGeometry,
      new THREE.LineBasicMaterial({
        color: palette.path,
        transparent: true,
        opacity: 0.42,
      }),
    )
    scene.add(pathLine)

    const travelledGeometry = new THREE.BufferGeometry().setFromPoints(positions)
    travelledGeometry.setDrawRange(0, 1)
    const travelledLine = new THREE.Line(
      travelledGeometry,
      new THREE.LineBasicMaterial({ color: palette.travelled }),
    )
    scene.add(travelledLine)

    const endpointGeometry = new THREE.SphereGeometry(size * 0.025, 12, 8)
    const startPoint = new THREE.Mesh(
      endpointGeometry,
      new THREE.MeshBasicMaterial({ color: palette.start }),
    )
    startPoint.position.copy(positions[0])
    scene.add(startPoint)
    const endPoint = new THREE.Mesh(
      endpointGeometry.clone(),
      new THREE.MeshBasicMaterial({ color: palette.end }),
    )
    endPoint.position.copy(positions.at(-1) ?? positions[0])
    scene.add(endPoint)

    const marker = new THREE.Group()
    const markerGeometry = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(-0.065, -0.045, -0.13),
      new THREE.Vector3(0.065, -0.045, -0.13),
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(0.065, 0.045, -0.13),
      new THREE.Vector3(-0.065, 0.045, -0.13),
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(-0.065, -0.045, -0.13),
      new THREE.Vector3(-0.065, 0.045, -0.13),
      new THREE.Vector3(0.065, 0.045, -0.13),
      new THREE.Vector3(0.065, -0.045, -0.13),
    ].map((point) => point.multiplyScalar(size)))
    const markerBody = new THREE.Line(
      markerGeometry,
      new THREE.LineBasicMaterial({ color: palette.marker }),
    )
    marker.add(markerBody)
    scene.add(marker)
    markerRef.current = marker

    const resize = () => {
      const width = mount.clientWidth
      const height = mount.clientHeight
      if (!width || !height) return
      renderer.setSize(width, height, false)
      previewCamera.aspect = width / height
      previewCamera.updateProjectionMatrix()
    }
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(resize)
    observer?.observe(mount)
    resize()

    let animationFrame = 0
    let lastActionIndex = -1
    let lastProgressPercent = -1
    let lastActive = false
    const animate = () => {
      const video = videoRef.current
      const localSeconds = video
        ? video.currentTime - segmentStartSeconds
        : 0
      // The endpoint is the stationary pose after this camera segment. Clear
      // all action highlights as soon as the segment reaches that endpoint.
      const active = cameraSegmentIsActive(
        localSeconds,
        segmentDurationSeconds,
      )
      const progress = Math.min(
        1,
        Math.max(0, localSeconds / Math.max(segmentDurationSeconds, 0.001)),
      )
      const pathDurationMs =
        path.durationMs
        ?? frames.at(-1)?.t
        ?? Math.max(0, frames.length - 1) * 1000 / (path.sampleRate ?? 24)
      const sample = frameAtTime(frames, progress * pathDurationMs)
      if (sample.position && sample.quaternion && markerRef.current) {
        markerRef.current.position.copy(sample.position)
        markerRef.current.quaternion.copy(sample.quaternion)
      }
      travelledGeometry.setDrawRange(0, Math.max(1, sample.index + 1))
      const actionTime = active ? progress * pathDurationMs : -1
      const actionIndex = active
        ? keyEvents.findLastIndex((event) => event.t <= actionTime)
        : -1
      if (actionIndex !== lastActionIndex) {
        lastActionIndex = actionIndex
        setActions(active ? actionsAtTime(keyEvents, actionTime) : IDLE_ACTIONS)
      }
      const nextProgressPercent = Math.round(progress * 100)
      if (nextProgressPercent !== lastProgressPercent) {
        lastProgressPercent = nextProgressPercent
        setProgressPercent(nextProgressPercent)
      }
      if (active !== lastActive) {
        lastActive = active
        setIsActive(active)
      }
      renderer.render(scene, previewCamera)
      animationFrame = requestAnimationFrame(animate)
    }
    animationFrame = requestAnimationFrame(animate)

    return () => {
      cancelAnimationFrame(animationFrame)
      observer?.disconnect()
      pathGeometry.dispose()
      ;(pathLine.material as THREE.Material).dispose()
      travelledGeometry.dispose()
      ;(travelledLine.material as THREE.Material).dispose()
      endpointGeometry.dispose()
      endPoint.geometry.dispose()
      ;(startPoint.material as THREE.Material).dispose()
      ;(endPoint.material as THREE.Material).dispose()
      markerGeometry.dispose()
      ;(markerBody.material as THREE.Material).dispose()
      renderer.dispose()
      renderer.domElement.remove()
      markerRef.current = null
    }
  }, [frames, keyEvents, path.durationMs, path.sampleRate, segmentDurationSeconds, segmentStartSeconds, theme, videoRef, visible])

  if (frames.length === 0) return null
  if (!visible) {
    return (
      <button
        className="direction-hud-reveal"
        type="button"
        aria-label="Show camera path"
        title="Show camera path"
        onClick={onVisibilityToggle}
      >
        <Eye size={17} strokeWidth={1.8} />
        <span>Show camera</span>
      </button>
    )
  }

  return (
    <div className="camera-playback-overlay" aria-label="Camera action overlay">
      <div className="camera-key-overlay camera-key-overlay-left" aria-label="Camera movement">
        <div className="camera-key-grid">
          <Key label="W" active={actions.forward} />
          <Key label="A" active={actions.left} />
          <Key label="S" active={actions.backward} />
          <Key label="D" active={actions.right} />
        </div>
      </div>
      <div className="camera-key-overlay camera-key-overlay-right" aria-label="Camera rotation">
        <div className="camera-key-grid">
          <Key label="↑" active={actions.lookUp} />
          <Key label="←" active={actions.lookLeft} />
          <Key label="↓" active={actions.lookDown} />
          <Key label="→" active={actions.lookRight} />
        </div>
      </div>
      <aside
        className="direction-hud camera-trajectory-hud"
        aria-label="Camera path visualization"
      >
        <svg
          className="direction-hud-frame"
          viewBox="0 0 360 254"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <defs>
            <linearGradient
              id="camera-hud-surface"
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
              id="camera-hud-shadow"
              x="-20%"
              y="-20%"
              width="140%"
              height="150%"
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
            d="M18 1H342C351.4 1 359 8.6 359 18V236C359 245.4 351.4 253 342 253H18C8.6 253 1 245.4 1 236V18C1 8.6 8.6 1 18 1Z"
            fill="url(#camera-hud-surface)"
            filter="url(#camera-hud-shadow)"
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
            d="M326 253H342C351.4 253 359 245.4 359 236V225"
            vectorEffect="non-scaling-stroke"
          />
          <rect
            className="direction-hud-track"
            x="18"
            y="240"
            width="324"
            height="3"
            rx="1.5"
          />
          <rect
            className="direction-hud-progress"
            x="18"
            y="240"
            width={324 * progressPercent / 100}
            height="3"
            rx="1.5"
          />
        </svg>

        <div className="direction-hud-content camera-trajectory-hud-content">
          <header>
            <span className="direction-hud-title">
              <span className="direction-hud-icon">
                <Navigation size={13} strokeWidth={1.8} />
              </span>
              <span>
                <small>CAMERA PATH</small>
                <strong>Turn {String(turnNumber).padStart(2, '0')}</strong>
              </span>
            </span>
            <span className="direction-hud-tools">
              <span
                className={
                  isActive
                    ? 'direction-hud-state active'
                    : 'direction-hud-state'
                }
              >
                {isActive ? 'LIVE' : 'PLAYBACK'}
              </span>
              <button
                type="button"
                aria-label="Hide camera path"
                title="Hide camera path"
                onClick={onVisibilityToggle}
              >
                <EyeOff size={15} strokeWidth={1.8} />
              </button>
            </span>
          </header>
          <div className="camera-trajectory-body">
            <div ref={mountRef} className="camera-trajectory-canvas" />
            <div className="camera-trajectory-footer">
              <span>{path.name}</span>
              <strong>{progressPercent}%</strong>
            </div>
          </div>
        </div>
      </aside>
    </div>
  )
}
