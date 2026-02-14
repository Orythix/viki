import React, { useRef, useMemo, useState, useEffect, Suspense } from 'react'
import { useFrame } from '@react-three/fiber'
import { Float, useGLTF } from '@react-three/drei'
import * as THREE from 'three'

// GLB face model: default to local file in public folder; override with VITE_VIKI_HOLOGRAM_FACE_GLB for a different URL
function getFaceGlbUrl() {
  const env = import.meta.env.VITE_VIKI_HOLOGRAM_FACE_GLB
  if (env) return env
  if (typeof window !== 'undefined') {
    const base = (import.meta.env.BASE_URL || '/').replace(/\/$/, '') || ''
    return `${window.location.origin}${base}/models/hologram-face.glb`
  }
  return '/models/hologram-face.glb'
}
// Resolved at runtime in the component so window/origin is available

const hologramCyan = new THREE.Color(0x00d4ff)
const hologramPurple = new THREE.Color(0x9966ff)
const skinTint = new THREE.Color(0x4dd0e1) // soft teal for skin-like base

function createHologramShaderMaterial() {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    side: THREE.FrontSide,
    uniforms: {
      uColor: { value: hologramCyan.clone() },
      uRimColor: { value: hologramPurple.clone() },
      uSkinTint: { value: skinTint.clone() },
      uTime: { value: 0 }
    },
    vertexShader: `
      varying vec3 vNormal;
      varying vec3 vViewPosition;
      void main() {
        vNormal = normalize(normalMatrix * normal);
        vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
        vViewPosition = -mvPosition.xyz;
        gl_Position = projectionMatrix * mvPosition;
      }
    `,
    fragmentShader: `
      uniform vec3 uColor;
      uniform vec3 uRimColor;
      uniform vec3 uSkinTint;
      uniform float uTime;
      varying vec3 vNormal;
      varying vec3 vViewPosition;
      void main() {
        vec3 viewDir = normalize(vViewPosition);
        float fresnel = 1.0 - max(dot(viewDir, vNormal), 0.0);
        fresnel = pow(fresnel, 1.8);
        float scan = step(0.97, fract((gl_FragCoord.y + uTime * 30.0) * 0.02));
        float alpha = 0.35 + fresnel * 0.55 + scan * 0.06;
        vec3 col = mix(uSkinTint, uColor, 0.5);
        col = mix(col, uRimColor, fresnel);
        col += scan * uRimColor * 0.5;
        gl_FragColor = vec4(col, alpha);
      }
    `
  })
}

// Hologram shader with slight skin-like base tone for more human feel
const hologramFaceVertexShader = `
  varying vec3 vNormal;
  varying vec3 vViewPosition;
  void main() {
    vNormal = normalize(normalMatrix * normal);
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    vViewPosition = -mvPosition.xyz;
    gl_Position = projectionMatrix * mvPosition;
  }
`
const hologramFaceFragmentShader = `
  uniform vec3 uColor;
  uniform vec3 uRimColor;
  uniform vec3 uSkinTint;
  uniform float uTime;
  varying vec3 vNormal;
  varying vec3 vViewPosition;
  void main() {
    vec3 viewDir = normalize(vViewPosition);
    float fresnel = 1.0 - max(dot(viewDir, vNormal), 0.0);
    fresnel = pow(fresnel, 1.8);
    float scan = step(0.97, fract((gl_FragCoord.y + uTime * 30.0) * 0.02));
    float alpha = 0.35 + fresnel * 0.55 + scan * 0.06;
    vec3 col = mix(uSkinTint, uColor, 0.5);
    col = mix(col, uRimColor, fresnel);
    col += scan * uRimColor * 0.5;
    gl_FragColor = vec4(col, alpha);
  }
`

function HologramFaceMaterial() {
  const materialRef = useRef()
  useFrame((_, delta) => {
    if (materialRef.current?.uniforms?.uTime) materialRef.current.uniforms.uTime.value += delta
  })
  return (
    <shaderMaterial
      ref={materialRef}
      transparent
      depthWrite={false}
      side={THREE.FrontSide}
      uniforms={{
        uColor: { value: hologramCyan },
        uRimColor: { value: hologramPurple },
        uSkinTint: { value: skinTint },
        uTime: { value: 0 }
      }}
      vertexShader={hologramFaceVertexShader}
      fragmentShader={hologramFaceFragmentShader}
    />
  )
}

// Human-like head: ellipsoid (slightly taller, less deep)
function Head() {
  const groupRef = useRef()
  useFrame((_, delta) => {
    if (groupRef.current) groupRef.current.rotation.y += delta * 0.12
  })
  return (
    <Float speed={1.2} floatIntensity={0.08}>
      <group ref={groupRef}>
        <mesh scale={[0.98, 1.05, 0.92]}>
          <sphereGeometry args={[1, 36, 32]} />
          <HologramFaceMaterial />
        </mesh>
        <mesh scale={[0.982, 1.052, 0.922]}>
          <sphereGeometry args={[1, 20, 14]} />
          <meshBasicMaterial color={hologramCyan} wireframe transparent opacity={0.08} />
        </mesh>
      </group>
    </Float>
  )
}

// Nose bridge and tip
function Nose() {
  return (
    <group position={[0, -0.02, 0.96]}>
      <mesh position={[0, 0.08, 0.08]} rotation={[0.35, 0, 0]}>
        <cylinderGeometry args={[0.04, 0.06, 0.2, 10]} />
        <meshBasicMaterial color={hologramCyan} transparent opacity={0.7} />
      </mesh>
      <mesh position={[0, 0.02, 0.18]}>
        <sphereGeometry args={[0.06, 12, 10]} />
        <meshBasicMaterial color={hologramCyan} transparent opacity={0.75} />
      </mesh>
    </group>
  )
}

// Eyebrows
function Eyebrows() {
  const tubeGeo = useMemo(() => {
    const curve = new THREE.CatmullRomCurve3([
      new THREE.Vector3(-0.08, 0, 0),
      new THREE.Vector3(-0.02, 0.01, 0),
      new THREE.Vector3(0.02, 0.01, 0),
      new THREE.Vector3(0.08, 0, 0)
    ])
    return new THREE.TubeGeometry(curve, 6, 0.018, 6, false)
  }, [])
  return (
    <group position={[0, 0.28, 0.92]}>
      <mesh position={[-0.22, 0.02, 0]} geometry={tubeGeo}>
        <meshBasicMaterial color={hologramPurple} transparent opacity={0.6} />
      </mesh>
      <mesh position={[0.22, 0.02, 0]} geometry={tubeGeo}>
        <meshBasicMaterial color={hologramPurple} transparent opacity={0.6} />
      </mesh>
    </group>
  )
}

// Eyes with iris and slight depth
function Eyes() {
  return (
    <group position={[0, 0.12, 0.92]}>
      <group position={[-0.2, 0.06, 0]}>
        <mesh>
          <sphereGeometry args={[0.1, 20, 16, 0, Math.PI * 2, 0, Math.PI * 0.6]} />
          <meshBasicMaterial color={hologramCyan} transparent opacity={0.9} />
        </mesh>
        <mesh position={[0, 0, 0.06]}>
          <circleGeometry args={[0.04, 16]} />
          <meshBasicMaterial color={hologramPurple} transparent opacity={0.95} side={THREE.DoubleSide} />
        </mesh>
      </group>
      <group position={[0.2, 0.06, 0]}>
        <mesh>
          <sphereGeometry args={[0.1, 20, 16, 0, Math.PI * 2, 0, Math.PI * 0.6]} />
          <meshBasicMaterial color={hologramCyan} transparent opacity={0.9} />
        </mesh>
        <mesh position={[0, 0, 0.06]}>
          <circleGeometry args={[0.04, 16]} />
          <meshBasicMaterial color={hologramPurple} transparent opacity={0.95} side={THREE.DoubleSide} />
        </mesh>
      </group>
    </group>
  )
}

// Lips: upper and lower suggestion
function Mouth() {
  return (
    <group position={[0, -0.2, 0.94]}>
      <mesh rotation={[0, 0, Math.PI / 2]}>
        <torusGeometry args={[0.07, 0.022, 8, 16, Math.PI]} />
        <meshBasicMaterial color={hologramCyan} transparent opacity={0.8} side={THREE.DoubleSide} />
      </mesh>
      <mesh position={[0, -0.012, 0.002]} rotation={[0, 0, Math.PI / 2]}>
        <ringGeometry args={[0.04, 0.07, 8, 1, 0, Math.PI]} />
        <meshBasicMaterial color={hologramPurple} transparent opacity={0.6} side={THREE.DoubleSide} />
      </mesh>
    </group>
  )
}

// Subtle cheekbones
function Cheeks() {
  return (
    <group position={[0, -0.08, 0.88]}>
      <mesh position={[-0.32, 0.02, 0.06]}>
        <sphereGeometry args={[0.12, 16, 12, 0, Math.PI * 2, 0, Math.PI * 0.4]} />
        <meshBasicMaterial color={skinTint} transparent opacity={0.25} />
      </mesh>
      <mesh position={[0.32, 0.02, 0.06]}>
        <sphereGeometry args={[0.12, 16, 12, 0, Math.PI * 2, 0, Math.PI * 0.4]} />
        <meshBasicMaterial color={skinTint} transparent opacity={0.25} />
      </mesh>
    </group>
  )
}

// Fuller, more natural hair
function Hair() {
  const hairColor = new THREE.Color(0x5a4a8a)
  return (
    <group>
      <group position={[0, 0.52, 0.22]} rotation={[0.22, 0, 0]}>
        <mesh>
          <sphereGeometry args={[0.82, 32, 20, 0, Math.PI * 2, 0, Math.PI * 0.48]} />
          <meshPhysicalMaterial
            color={hairColor}
            emissive={hairColor}
            emissiveIntensity={0.22}
            transparent
            opacity={0.88}
            roughness={0.4}
            metalness={0}
          />
        </mesh>
      </group>
      <group position={[0.38, 0.15, 0.68]} rotation={[0, 0, -0.35]}>
        <mesh>
          <cylinderGeometry args={[0.06, 0.11, 0.55, 14]} />
          <meshPhysicalMaterial color={hairColor} emissive={hairColor} emissiveIntensity={0.18} transparent opacity={0.82} />
        </mesh>
      </group>
      <group position={[-0.38, 0.15, 0.68]} rotation={[0, 0, 0.35]}>
        <mesh>
          <cylinderGeometry args={[0.06, 0.11, 0.55, 14]} />
          <meshPhysicalMaterial color={hairColor} emissive={hairColor} emissiveIntensity={0.18} transparent opacity={0.82} />
        </mesh>
      </group>
      <group position={[0, 0.68, 0.35]} rotation={[0.15, 0, 0]}>
        <mesh>
          <sphereGeometry args={[0.35, 20, 12, 0, Math.PI * 2, 0, Math.PI * 0.5]} />
          <meshPhysicalMaterial color={hairColor} emissive={hairColor} emissiveIntensity={0.2} transparent opacity={0.85} />
        </mesh>
      </group>
    </group>
  )
}

function Neck() {
  const neckColor = new THREE.Color(0x3db8c4)
  return (
    <group position={[0, -0.48, 0.86]}>
      <mesh>
        <cylinderGeometry args={[0.32, 0.4, 0.38, 24]} />
        <meshPhysicalMaterial
          color={neckColor}
          emissive={neckColor}
          emissiveIntensity={0.12}
          transparent
          opacity={0.85}
          roughness={0.35}
        />
      </mesh>
    </group>
  )
}

function ScanlineOverlay() {
  const materialRef = useRef()
  useFrame((_, delta) => {
    if (materialRef.current?.uniforms?.uTime) materialRef.current.uniforms.uTime.value += delta
  })
  return (
    <mesh position={[0, 0, 1.5]} renderOrder={100}>
      <planeGeometry args={[4, 4]} />
      <shaderMaterial
        ref={materialRef}
        transparent
        depthWrite={false}
        side={THREE.DoubleSide}
        uniforms={{ uTime: { value: 0 } }}
        vertexShader={`
          varying vec2 vUv;
          void main() {
            vUv = uv;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
          }
        `}
        fragmentShader={`
          uniform float uTime;
          varying vec2 vUv;
          void main() {
            float scan = step(0.98, fract((vUv.y + uTime * 0.5) * 80.0));
            gl_FragColor = vec4(0.0, 0.85, 1.0, scan * 0.06);
          }
        `}
      />
    </mesh>
  )
}

// Procedural face (built from primitives) — used when no GLB or as fallback
function ProceduralFace() {
  return (
    <>
      <Head />
      <Nose />
      <Eyebrows />
      <Eyes />
      <Mouth />
      <Cheeks />
      <Hair />
      <Neck />
    </>
  )
}

// AI-generated or custom 3D face from GLB/GLTF — hologram material applied, centered and scaled
function AIGeneratedFaceWrapper({ url }) {
  // Disable Draco and MeshOpt so plain GLB files load reliably
  const { scene } = useGLTF(url, false, false)
  const groupRef = useRef()
  const hologramMaterial = useMemo(() => createHologramShaderMaterial(), [])

  const clonedScene = useMemo(() => {
    const clone = scene.clone()
    clone.traverse((child) => {
      if (child.isMesh) {
        child.material = hologramMaterial
      }
    })
    return clone
  }, [scene, hologramMaterial])

  useFrame((_, delta) => {
    if (hologramMaterial?.uniforms?.uTime) hologramMaterial.uniforms.uTime.value += delta
  })

  const { scale, position } = useMemo(() => {
    const b = new THREE.Box3().setFromObject(clonedScene)
    const c = b.getCenter(new THREE.Vector3())
    const s = b.getSize(new THREE.Vector3())
    const maxDim = Math.max(s.x, s.y, s.z) || 1
    const scale = 1.2 / maxDim
    return { scale: [scale, scale, scale], position: [-c.x * scale, -c.y * scale, -c.z * scale] }
  }, [clonedScene])

  return (
    <Float speed={1.2} floatIntensity={0.08}>
      <group ref={groupRef}>
        <primitive object={clonedScene} scale={scale} position={position} />
      </group>
    </Float>
  )
}

export default function HologramGirl3D({ mode }) {
  const [glbError, setGlbError] = useState(false)
  const faceGlbUrl = useMemo(() => getFaceGlbUrl(), [])
  const useGLB = faceGlbUrl && !glbError

  useEffect(() => {
    if (faceGlbUrl) useGLTF.preload(faceGlbUrl, false, false)
  }, [faceGlbUrl])

  return (
    <>
      <ambientLight intensity={0.5} />
      <pointLight position={[2, 1.5, 2]} intensity={1.0} color={0x00d4ff} />
      <pointLight position={[-1.8, -0.3, 1.2]} intensity={0.5} color={0x9966ff} />
      <pointLight position={[0, 1, 1.5]} intensity={0.4} color={0xffffff} />
      {useGLB ? (
        <Suspense fallback={<ProceduralFace />}>
          <ErrorBoundary fallback={<ProceduralFace />} onError={() => setGlbError(true)}>
            <AIGeneratedFaceWrapper url={faceGlbUrl} />
          </ErrorBoundary>
        </Suspense>
      ) : (
        <ProceduralFace />
      )}
      <ScanlineOverlay />
    </>
  )
}

class ErrorBoundary extends React.Component {
  static getDerivedStateFromError() {
    return { hasError: true }
  }
  state = { hasError: false }
  componentDidCatch(err) {
    this.props.onError?.(err)
  }
  render() {
    if (this.state.hasError) return this.props.fallback ?? null
    return this.props.children
  }
}
