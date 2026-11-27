"use client";

import { Environment, Lightformer, PerformanceMonitor, Trail } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Bloom, EffectComposer, Noise, Vignette } from "@react-three/postprocessing";
import { Component, Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import * as THREE from "three";
import { RETRY_WAITS } from "@/content/story";
import { BOOT_END, cameraPosition, clamp, smooth, span, story } from "@/lib/store";

/*
 * One sculpture for the whole story: an hour made of 60 minute-slabs, arranged as a ring that is open at its end, like
 * [start, end). Each chapter gives every slab a new place and colour; between chapters the slabs travel from one
 * arrangement to the next, so the reader watches one object change its mind rather than a set of separate diagrams.
 * Two comets are the two requests.
 */

const N = 60;
const C = {
  a: new THREE.Color("#6d82ff"),
  b: new THREE.Color("#e6ebff"),
  booked: new THREE.Color("#3fe0a8"),
  conflict: new THREE.Color("#ff6a4d"),
  waiting: new THREE.Color("#f5bd4f"),
  dim: new THREE.Color("#2a3352"),
  steel: new THREE.Color("#8d98b8"),
};

type Pose = { p: THREE.Vector3; r: THREE.Euler; s: THREE.Vector3; c: THREE.Color; glow: number };
type Comets = [THREE.Vector3, THREE.Vector3];
const TAU = Math.PI * 2;
const OPEN = 0.86; // share of the ring that is drawn: the end stays open

const pose = (): Pose => ({ p: new THREE.Vector3(), r: new THREE.Euler(), s: new THREE.Vector3(1, 1, 1), c: new THREE.Color(), glow: 1 });

/* ───────── arrangements: (slab index, time, out) → out ───────── */

function ring(i: number, out: Pose, radius = 3.1, from = 0) {
  const t = i / (N - 1);
  const a = from + Math.PI * 0.62 - t * TAU * OPEN;
  out.p.set(Math.cos(a) * radius, Math.sin(a) * radius, 0);
  out.r.set(0, 0, a);
  // the first slab is the closed start: the tallest; the hour thins out toward its open end
  out.s.set(i === 0 ? 1.9 : 1.15 - t * 0.55, i === 0 ? 0.16 : 0.07, 0.62 - t * 0.3);
  return a;
}

type Layout = (i: number, time: number, out: Pose) => void;

const LAYOUTS: Layout[] = [
  // 0 · one hour, booked once the reader starts scrolling
  (i, time, out) => {
    ring(i, out, 3.1, time * 0.05);
    const booked = span(story.progress[0], 0.15, 0.6);
    out.c.copy(C.a).lerp(C.booked, booked * span(i, 0, 3) + booked * (1 - i / N) * 0.9);
    out.glow = i === 0 ? 2.2 : 1.1 - (i / N) * 0.6;
  },
  // 1 · daylight page covers this
  (i, time, out) => {
    ring(i, out, 3.4, time * 0.05);
    out.c.copy(C.a);
    out.glow = 0.8;
  },
  // 2 · two bookings land in one hour: two rings collide
  (i, time, out) => {
    const k = story.progress[2];
    const second = i % 2 === 1;
    ring(i, out, 2.7, time * 0.04 + (second ? 0.3 : 0));
    const apart = 1.8 * (1 - span(k, 0.45, 0.85));
    out.p.x += second ? apart : -apart;
    out.p.z += second ? 0.4 : -0.4;
    const collide = span(k, 0.5, 0.9);
    out.c.copy(second ? C.b : C.a).lerp(C.conflict, collide);
    out.glow = 1 + collide * 0.8;
  },
  // 3 · ordered locks: the hour straightens into four rows taken in order
  (i, _t, out) => {
    const stage = Math.floor(i / 15);
    const within = i % 15;
    out.p.set(-5.4 + stage * 3.6 + (within % 5) * 0.42, 1 - Math.floor(within / 5) * 0.55, 0);
    out.r.set(0.35, -0.4, 0);
    out.s.set(0.34, 0.4, 0.34);
    const current = Math.min(3, Math.floor(story.progress[3] * 4));
    const lit = stage < current ? 0.4 : stage === current ? 1 : 0;
    out.c.copy(C.dim).lerp(stage === current ? C.waiting : C.a, lit);
    out.glow = 0.6 + lit * 1.4;
  },
  // 4 · the database's time track; follows the reader's range control
  (i, _t, out) => {
    const hour = 8 + (i / (N - 1)) * 5; // 08:00 to 13:00
    const held = hour >= 10 && hour < 11;
    const tried = hour >= story.attempt && hour < story.attempt + 1;
    const refused = story.attempt < 11 && 10 < story.attempt + 1;
    out.p.set((hour - 10.5) * 1.15, held ? 0 : tried ? (refused ? 1.35 : 0) : -1.2, tried && !held ? 0.6 : 0);
    out.r.set(0, 0, 0);
    out.s.set(0.13, held || tried ? 1.1 : 0.32, 0.6);
    out.c.copy(held ? C.a : tried ? (refused ? C.conflict : C.booked) : C.dim);
    out.glow = held || tried ? 1.6 : 0.5;
  },
  // 5 · deadlock: two small loops, each waiting on the other
  (i, time, out) => {
    const k = story.progress[5];
    const second = i >= N / 2;
    const t = (i % (N / 2)) / (N / 2);
    const tighten = span(k, 0.2, 0.55);
    const queue = span(k, 0.72, 0.95);
    const a = t * TAU + time * 0.35 * (second ? -1 : 1) + k * 6;
    const r = 1.8 - tighten * 0.5;
    out.p.set(Math.cos(a) * r + (second ? 1 : -1) * (1.2 - tighten * 0.4), Math.sin(a) * r, 0);
    if (second) out.p.set(out.p.x, out.p.z, out.p.y);
    out.r.set(second ? Math.PI / 2 : 0, 0, a);
    out.s.set(0.55, 0.08, 0.32);
    // once the lock is back, both loops line up into one queue
    if (queue > 0) {
      const line = new THREE.Vector3(-5 + (i / N) * 10, 0, 0);
      out.p.lerp(line, queue);
    }
    out.c.copy(second ? C.b : C.a).lerp(C.conflict, tighten * (1 - queue)).lerp(C.booked, queue);
    out.glow = 1 + tighten * 1.2;
  },
  // 6 · retries, drawn to scale: ten gates at their true spacing
  (i, _t, out) => {
    const total = RETRY_WAITS.reduce((x, y) => x + y, 0);
    const gate = Math.floor(i / 6);
    const minute = RETRY_WAITS.slice(0, gate).reduce((x, y) => x + y, 0);
    const a = ((i % 6) / 6) * TAU;
    out.p.set(-5.5 + (minute / total) * 11, Math.cos(a) * 0.9, Math.sin(a) * 0.9);
    out.r.set(a, 0, 0);
    out.s.set(0.06, 0.5, 0.12);
    const passed = span(story.progress[6], 0.05, 0.95) * total >= minute;
    out.c.copy(passed ? (gate === 9 ? C.conflict : C.waiting) : C.dim);
    out.glow = passed ? 1.5 : 0.5;
  },
  // 7 · who may see what: rows sink out of view for a viewer who may not read them
  (i, _t, out) => {
    const row = Math.floor(i / 15);
    const col = i % 15;
    const visible = story.role === "mentor" ? row < 2 : true;
    const own = story.role === "admin" || (story.role === "mentor" ? visible : row === 0 || row === 3);
    out.p.set(-2.6 + col * 0.37, 1.4 - row * 0.9, visible ? 0 : -4);
    out.r.set(0, 0, 0);
    out.s.set(0.28, 0.55, 0.36);
    out.c.copy(!visible ? C.dim : own ? C.a : C.steel);
    out.glow = visible ? (own ? 1.4 : 0.7) : 0.2;
  },
  // 8 · daylight page covers this
  (i, time, out) => {
    ring(i, out, 3.4, time * 0.05);
    out.c.copy(C.dim);
    out.glow = 0.5;
  },
  // 9 · the mark: one block ends exactly where the next begins
  (i, _t, out) => {
    const second = i >= N / 2;
    const k = i % (N / 2);
    out.p.set((second ? 0.18 : -2.98) + (k % 10) * 0.31, (second ? -1.1 : 0.4) + Math.floor(k / 10) * 0.28, 0);
    out.r.set(0, 0, 0);
    out.s.set(0.26, 0.22, 0.6);
    out.c.copy(second ? C.booked : C.a);
    out.glow = 1.3;
  },
];

/* Comets: where the two requests are in each chapter. */
function comets(chapter: number, time: number, out: Comets) {
  const orbit = (v: THREE.Vector3, phase: number, r: number) => v.set(Math.cos(time * 0.6 + phase) * r, Math.sin(time * 0.6 + phase) * r * 0.5, Math.sin(time * 0.6 + phase) * 1.5);
  switch (chapter) {
    case 0: {
      const k = story.progress[0];
      orbit(out[0], 0, 4 + k);
      orbit(out[1], Math.PI, 4.6 + k * 2);
      break;
    }
    case 2: {
      const k = span(story.progress[2], 0.1, 0.7);
      out[0].set(-4 + 3.4 * k, 2.5 - 2.5 * k, 1);
      out[1].set(4 - 3.4 * k, 2.8 - 2.6 * k, 1);
      break;
    }
    case 5: {
      const a = time * 1.4 + story.progress[5] * 9;
      out[0].set(Math.cos(a) * 1.4, Math.sin(a) * 1.4, 1.2);
      out[1].set(Math.cos(a + Math.PI) * 1.4, Math.sin(a + Math.PI) * 1.4, 1.2);
      break;
    }
    case 6:
      out[0].set(-5.5 + span(story.progress[6], 0.05, 0.95) * 11, 0, 0);
      out[1].set(0, -30, 0);
      break;
    default:
      orbit(out[0], 0, 5);
      orbit(out[1], Math.PI, 5.5);
  }
}

/* Camera framing per chapter: how far, and where the sculpture sits on screen (share of width, share of height). */
const FRAME: Array<{ d: number; x: number; y: number; tilt: number }> = [
  { d: 16, x: 0.24, y: 0.04, tilt: 0.3 },
  { d: 16, x: 0.2, y: 0, tilt: 0.3 },
  { d: 17, x: 0.24, y: 0.04, tilt: 0.25 },
  { d: 19, x: 0.2, y: 0.02, tilt: 0.12 },
  { d: 16, x: 0.0, y: 0.26, tilt: 0.05 },
  { d: 15, x: 0.24, y: 0.04, tilt: 0.35 },
  { d: 16, x: 0.12, y: 0.12, tilt: 0.2 },
  { d: 17, x: 0.3, y: 0.02, tilt: 0.1 },
  { d: 16, x: 0.2, y: 0, tilt: 0.3 },
  { d: 14, x: 0.26, y: 0.2, tilt: 0.06 },
];

function Hour() {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const a = useMemo(() => Array.from({ length: N }, pose), []);
  const b = useMemo(() => Array.from({ length: N }, pose), []);
  const scatter = useMemo(() => {
    let seed = 11;
    const r = () => ((seed = (seed * 16807) % 2147483647) / 2147483647) * 2 - 1;
    return Array.from({ length: N }, () => new THREE.Vector3(r() * 14, r() * 9, r() * 10 - 4));
  }, []);
  const tmp = useMemo(() => ({ m: new THREE.Matrix4(), q: new THREE.Quaternion(), qb: new THREE.Quaternion(), c: new THREE.Color(), p: new THREE.Vector3(), s: new THREE.Vector3() }), []);
  const current = useRef(0);

  useFrame(({ clock }, delta) => {
    const target = cameraPosition();
    current.current += (target - current.current) * (1 - Math.exp(-Math.min(delta, 0.05) * 6));
    const position = current.current;
    const i0 = Math.min(LAYOUTS.length - 1, Math.floor(position));
    const i1 = Math.min(LAYOUTS.length - 1, i0 + 1);
    const k = smooth(position - i0);
    const time = clock.elapsedTime;
    const boot = story.boot < BOOT_END ? span(story.boot, 0.2, 3.6) : 1;
    const m = mesh.current!;

    for (let i = 0; i < N; i++) {
      LAYOUTS[i0](i, time, a[i]);
      LAYOUTS[i1](i, time, b[i]);
      // each slab leaves a little after its neighbour, so changes ripple along the hour
      const stagger = clamp(k * 1.6 - (i / N) * 0.6);
      const e = smooth(stagger);
      tmp.p.lerpVectors(a[i].p, b[i].p, e);
      tmp.p.y += Math.sin(stagger * Math.PI) * 0.6;
      if (boot < 1) tmp.p.lerpVectors(scatter[i], tmp.p, smooth(clamp(boot * 1.4 - (i / N) * 0.4)));
      tmp.q.setFromEuler(a[i].r);
      tmp.qb.setFromEuler(b[i].r);
      tmp.q.slerp(tmp.qb, e);
      tmp.s.lerpVectors(a[i].s, b[i].s, e);
      tmp.m.compose(tmp.p, tmp.q, tmp.s);
      m.setMatrixAt(i, tmp.m);
      const glow = a[i].glow + (b[i].glow - a[i].glow) * e;
      tmp.c.copy(a[i].c).lerp(b[i].c, e).multiplyScalar(glow * (0.25 + boot * 0.75));
      m.setColorAt(i, tmp.c);
    }
    m.instanceMatrix.needsUpdate = true;
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
  });

  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, N]} frustumCulled={false}>
      <boxGeometry args={[1, 1, 1]} />
      <meshPhysicalMaterial roughness={0.12} metalness={0.05} clearcoat={1} clearcoatRoughness={0.08} toneMapped={false} />
    </instancedMesh>
  );
}

function Comet({ which }: { which: 0 | 1 }) {
  const ref = useRef<THREE.Mesh>(null);
  const out = useMemo<Comets>(() => [new THREE.Vector3(), new THREE.Vector3()], []);
  const from = useMemo<Comets>(() => [new THREE.Vector3(), new THREE.Vector3()], []);
  useFrame(({ clock }) => {
    const position = cameraPosition();
    const i0 = Math.floor(position);
    const k = smooth(position - i0);
    const time = clock.elapsedTime;
    comets(i0, time, from);
    comets(Math.min(9, i0 + 1), time, out);
    const v = ref.current!.position.lerpVectors(from[which], out[which], k);
    if (story.boot < BOOT_END) {
      // the opening: both requests streak in from opposite sides
      const t = span(story.boot, 0.3, 3.4);
      v.lerp(new THREE.Vector3(which ? 16 : -16, which ? -4 : 5, -6), 1 - t);
    }
  });
  const color = which ? "#e6ebff" : "#7d90ff";
  return (
    <Trail width={1.6} length={7} color={color} attenuation={(w) => w * w} decay={1.4}>
      <mesh ref={ref}>
        <sphereGeometry args={[0.09, 16, 16]} />
        <meshBasicMaterial color={new THREE.Color(color).multiplyScalar(4)} toneMapped={false} />
      </mesh>
    </Trail>
  );
}

function Rig() {
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera;
  const size = useThree((s) => s.size);
  const current = useRef(0);
  const look = useMemo(() => new THREE.Vector3(), []);

  useFrame(({ clock }, delta) => {
    current.current += (cameraPosition() - current.current) * (1 - Math.exp(-Math.min(delta, 0.05) * 5));
    const position = current.current;
    const i = Math.min(9, Math.floor(position));
    const j = Math.min(9, i + 1);
    const k = smooth(position - i);
    const f = (key: "d" | "x" | "y" | "tilt") => FRAME[i][key] + (FRAME[j][key] - FRAME[i][key]) * k;
    const portrait = size.width / size.height < 1;
    const boot = story.boot < BOOT_END ? 1 - span(story.boot, 1.2, BOOT_END - 0.3) : 0;
    const d = f("d") * (portrait ? 1.35 : 1) + boot * 6;
    const t = clock.elapsedTime;
    const yaw = Math.sin(t * 0.08) * 0.12 + story.pointer.x * 0.08 + boot * 0.8;
    const pitch = f("tilt") + story.pointer.y * 0.04;
    camera.position.set(Math.sin(yaw) * d, Math.sin(pitch) * d, Math.cos(yaw) * Math.cos(pitch) * d);
    camera.lookAt(look.set(0, 0, 0));
    camera.rotateZ(boot * -0.15);
    const sx = portrait ? 0 : f("x") * (1 - boot);
    const sy = portrait ? -0.22 : f("y") * (1 - boot);
    camera.setViewOffset(size.width, size.height, -sx * size.width, -sy * size.height, size.width, size.height);
  });
  return null;
}

function Dust({ count }: { count: number }) {
  const ref = useRef<THREE.Points>(null);
  const [positions] = useState(() => {
    const data = new Float32Array(count * 3);
    let seed = 3;
    const r = () => ((seed = (seed * 16807) % 2147483647) / 2147483647) * 2 - 1;
    for (let i = 0; i < count; i++) data.set([r() * 22, r() * 14, r() * 16 - 6], i * 3);
    return data;
  });
  useFrame((_, delta) => {
    ref.current!.rotation.y += delta * 0.008;
    ref.current!.position.y = -cameraPosition() * 0.6;
  });
  return (
    <points ref={ref} frustumCulled={false}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial size={0.03} color="#9aa8ff" transparent opacity={0.45} sizeAttenuation depthWrite={false} />
    </points>
  );
}

/* Stops drawing while an opaque daylight page covers the view, or the tab is hidden. */
function Governor() {
  const setFrameloop = useThree((s) => s.setFrameloop);
  useEffect(() => {
    let frame = 0;
    const check = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const covered = [1, 8].some((i) => {
          const box = document.querySelector(`[data-chapter="${i}"]`)?.getBoundingClientRect();
          return box && box.top <= 0 && box.bottom >= window.innerHeight;
        });
        setFrameloop(covered || document.hidden ? "never" : "always");
      });
    };
    window.addEventListener("scroll", check, { passive: true });
    document.addEventListener("visibilitychange", check);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", check);
      document.removeEventListener("visibilitychange", check);
    };
  }, [setFrameloop]);
  return null;
}

class Boundary extends Component<{ onFail: () => void; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() { this.props.onFail(); }
  render() { return this.state.failed ? null : this.props.children; }
}

const fail = () => {
  document.documentElement.dataset.webgl = "off";
  window.dispatchEvent(new Event("world:failed"));
};

export default function World() {
  const [rich, setRich] = useState(true);
  const [small, setSmall] = useState(false);
  useEffect(() => {
    setSmall(window.innerWidth < 800);
    if (!document.createElement("canvas").getContext("webgl2")) fail();
    const move = (e: PointerEvent) => {
      story.pointer.x = (e.clientX / window.innerWidth) * 2 - 1;
      story.pointer.y = 1 - (e.clientY / window.innerHeight) * 2;
    };
    window.addEventListener("pointermove", move, { passive: true });
    return () => window.removeEventListener("pointermove", move);
  }, []);

  return (
    <div className="world" aria-hidden="true">
      <Boundary onFail={fail}>
        <Canvas
          dpr={[1, rich && !small ? 1.75 : 1.25]}
          camera={{ fov: 32, near: 0.1, far: 80, position: [0, 2, 12] }}
          gl={{ antialias: true, powerPreference: "high-performance" }}
          onCreated={({ gl }) => {
            gl.domElement.addEventListener("webglcontextlost", fail, { once: true });
            window.dispatchEvent(new Event("world:ready"));
          }}
        >
          <color attach="background" args={["#05070d"]} />
          <fog attach="fog" args={["#05070d", 14, 34]} />
          <PerformanceMonitor onDecline={() => setRich(false)} />
          <ambientLight intensity={0.2} />
          <Suspense fallback={null}>
            <Environment resolution={256} frames={1}>
              <Lightformer form="rect" intensity={4} position={[0, 6, 2]} rotation={[Math.PI / 2, 0, 0]} scale={[12, 3, 1]} color="#dfe6ff" />
              <Lightformer form="rect" intensity={2.5} position={[-7, 0, 3]} rotation={[0, Math.PI / 2, 0]} scale={[10, 2, 1]} color="#6d82ff" />
              <Lightformer form="ring" intensity={1.5} position={[6, -2, 4]} scale={4} color="#3fe0a8" />
            </Environment>
            <Rig />
            <Hour />
            <Comet which={0} />
            <Comet which={1} />
            <Dust count={small ? 400 : 1200} />
          </Suspense>
          <Governor />
          {rich && (
            <EffectComposer multisampling={small ? 0 : 4}>
              <Bloom mipmapBlur intensity={1.1} luminanceThreshold={0.85} luminanceSmoothing={0.2} radius={0.7} />
              <Noise opacity={0.035} />
              <Vignette offset={0.25} darkness={0.8} />
            </EffectComposer>
          )}
        </Canvas>
      </Boundary>
    </div>
  );
}
