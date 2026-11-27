"use client";

import { useEffect, useRef } from "react";

const POINTS = 28;

const VERTEX = `#version 300 es
void main() {
  vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}`;

/*
 * A ribbon of light behind the pointer, and a half-open bracket that snaps around whatever can be pressed: a solid start
 * bar, top and bottom edges that fade out, no end. Output is premultiplied so it reads on both night and daylight pages.
 */
const FRAGMENT = `#version 300 es
precision highp float;
uniform vec2 trail[${POINTS}];
uniform vec4 box;      // x, y, width, height of the hovered control
uniform float hold;    // 0 free, 1 snapped to a control
uniform float energy;  // pointer speed
uniform float dpr;
uniform vec3 head, tail;
out vec4 color;

float segment(vec2 p, vec2 a, vec2 b, out float h) {
  vec2 pa = p - a, ba = b - a;
  h = clamp(dot(pa, ba) / max(dot(ba, ba), 0.0001), 0.0, 1.0);
  return length(pa - ba * h);
}

void main() {
  vec2 p = gl_FragCoord.xy;
  float ink = 0.0, along = 0.0;
  for (int i = 0; i < ${POINTS - 1}; i++) {
    float h;
    float d = segment(p, trail[i], trail[i + 1], h);
    float s = (float(i) + h) / float(${POINTS - 1});
    float width = mix(5.0, 0.4, s) * (1.0 + energy * 1.6) * dpr;
    float a = (smoothstep(width, width * 0.25, d) * 0.75 + exp(-d / (width * 2.4)) * 0.22) * pow(1.0 - s, 1.4);
    if (a > ink) { ink = a; along = s; }
  }
  ink *= (1.0 - hold) * smoothstep(0.0, 0.12, energy);

  // dot at the pointer, grows into the bracket
  float dot_ = smoothstep(5.5 * dpr, 3.5 * dpr, length(p - trail[0])) * (1.0 - hold) * 0.9;

  vec2 lo = box.xy - 7.0 * dpr, hi = box.xy + box.zw + 7.0 * dpr;
  float h;
  float start = smoothstep(2.6 * dpr, 1.4 * dpr, segment(p, vec2(lo.x, lo.y - 4.0 * dpr), vec2(lo.x, hi.y + 4.0 * dpr), h));
  float rails = max(
    smoothstep(1.4 * dpr, 0.4 * dpr, segment(p, lo, vec2(hi.x, lo.y), h)) * (1.0 - h),
    smoothstep(1.4 * dpr, 0.4 * dpr, segment(p, vec2(lo.x, hi.y), hi, h)) * (1.0 - h));
  float bracket = max(start, rails) * hold;

  float alpha = clamp(max(max(ink, dot_), bracket), 0.0, 1.0);
  vec3 tint = mix(head, tail, along * (1.0 - step(0.01, bracket)));
  color = vec4(tint * alpha, alpha);
}`;

/** Fine pointers only. The system cursor stays: this is a trace around it, never a replacement. */
export function CursorField() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !matchMedia("(pointer: fine)").matches) return;
    const gl = canvas.getContext("webgl2", { premultipliedAlpha: true, antialias: false, powerPreference: "low-power" });
    if (!gl) return;

    const program = gl.createProgram()!;
    for (const [type, source] of [[gl.VERTEX_SHADER, VERTEX], [gl.FRAGMENT_SHADER, FRAGMENT]] as const) {
      const shader = gl.createShader(type)!;
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      gl.attachShader(program, shader);
    }
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.warn("Cursor shader unavailable", gl.getProgramInfoLog(program));
      return;
    }
    gl.useProgram(program);
    const u = (name: string) => gl.getUniformLocation(program, name);
    const uniforms = { trail: u("trail"), box: u("box"), hold: u("hold"), energy: u("energy"), dpr: u("dpr"), head: u("head"), tail: u("tail") };
    gl.uniform3f(uniforms.head, 0.36, 0.45, 1.0);
    gl.uniform3f(uniforms.tail, 0.25, 0.88, 0.66);

    const dpr = Math.min(devicePixelRatio || 1, 1.5);
    const trail = new Float32Array(POINTS * 2).fill(-999);
    const pointer = { x: -999, y: -999, seen: false };
    const box = { x: 0, y: 0, w: 0, h: 0 };
    let target: Element | null = null;
    let hold = 0, energy = 0, frame = 0, last = 0;

    const resize = () => {
      canvas.width = Math.round(innerWidth * dpr);
      canvas.height = Math.round(innerHeight * dpr);
      gl.viewport(0, 0, canvas.width, canvas.height);
      wake();
    };

    const draw = (now: number) => {
      frame = 0;
      const dt = Math.min(0.05, (now - last) / 1000 || 0.016);
      last = now;
      const k = (rate: number) => 1 - Math.exp(-dt * rate);
      const before = [trail[0], trail[1]];
      trail[0] += (pointer.x - trail[0]) * k(30);
      trail[1] += (pointer.y - trail[1]) * k(30);
      let spread = 0;
      for (let i = 1; i < POINTS; i++) {
        trail[i * 2] += (trail[i * 2 - 2] - trail[i * 2]) * k(34);
        trail[i * 2 + 1] += (trail[i * 2 - 1] - trail[i * 2 + 1]) * k(34);
        spread += Math.abs(trail[i * 2] - trail[0]) + Math.abs(trail[i * 2 + 1] - trail[1]);
      }
      const speed = Math.hypot(trail[0] - before[0], trail[1] - before[1]) / dpr / (dt * 1000);
      energy += (Math.min(1, speed) - energy) * k(8);

      if (target && !target.isConnected) target = null;
      const wanted = target?.getBoundingClientRect();
      if (wanted) {
        const goal = { x: wanted.left * dpr, y: canvas.height - wanted.bottom * dpr, w: wanted.width * dpr, h: wanted.height * dpr };
        const rate = hold < 0.05 ? 1 : k(22);
        box.x += (goal.x - box.x) * rate;
        box.y += (goal.y - box.y) * rate;
        box.w += (goal.w - box.w) * rate;
        box.h += (goal.h - box.h) * rate;
      }
      hold += ((wanted ? 1 : 0) - hold) * k(14);

      gl.clearColor(0, 0, 0, 0);
      gl.disable(gl.SCISSOR_TEST);
      gl.clear(gl.COLOR_BUFFER_BIT);
      // only shade the part of the screen the effect can reach
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (let i = 0; i < POINTS; i++) {
        x0 = Math.min(x0, trail[i * 2]); x1 = Math.max(x1, trail[i * 2]);
        y0 = Math.min(y0, trail[i * 2 + 1]); y1 = Math.max(y1, trail[i * 2 + 1]);
      }
      if (hold > 0.01) {
        x0 = Math.min(x0, box.x); y0 = Math.min(y0, box.y);
        x1 = Math.max(x1, box.x + box.w); y1 = Math.max(y1, box.y + box.h);
      }
      const pad = 60 * dpr;
      gl.enable(gl.SCISSOR_TEST);
      gl.scissor(Math.floor(x0 - pad), Math.floor(y0 - pad), Math.ceil(Math.max(0, x1 - x0 + pad * 2)), Math.ceil(Math.max(0, y1 - y0 + pad * 2)));
      gl.uniform2fv(uniforms.trail, trail);
      gl.uniform4f(uniforms.box, box.x, box.y, box.w, box.h);
      gl.uniform1f(uniforms.hold, hold);
      gl.uniform1f(uniforms.energy, energy);
      gl.uniform1f(uniforms.dpr, dpr);
      if (pointer.seen) gl.drawArrays(gl.TRIANGLES, 0, 3);

      // rest when everything has caught up
      const settling = spread > 1 || energy > 0.01 || Math.abs(hold - (target ? 1 : 0)) > 0.005 || Math.hypot(pointer.x - trail[0], pointer.y - trail[1]) > 0.5;
      if (settling) wake();
    };
    function wake() { if (!frame && !document.hidden) frame = requestAnimationFrame(draw); }

    const move = (e: PointerEvent) => {
      if (e.pointerType === "touch") return;
      pointer.x = e.clientX * dpr;
      pointer.y = (innerHeight - e.clientY) * dpr;
      if (!pointer.seen) {
        for (let i = 0; i < POINTS; i++) trail.set([pointer.x, pointer.y], i * 2);
        pointer.seen = true;
      }
      target = (e.target as Element).closest?.("a, button, label, input[type=range]") ?? null;
      wake();
    };
    const leave = () => { pointer.seen = false; target = null; wake(); };
    const scroll = () => { target = null; wake(); };

    resize();
    addEventListener("resize", resize);
    addEventListener("pointermove", move, { passive: true });
    addEventListener("scroll", scroll, { passive: true });
    document.documentElement.addEventListener("pointerleave", leave);
    return () => {
      cancelAnimationFrame(frame);
      removeEventListener("resize", resize);
      removeEventListener("pointermove", move);
      removeEventListener("scroll", scroll);
      document.documentElement.removeEventListener("pointerleave", leave);
      gl.deleteProgram(program);
    };
  }, []);

  return <canvas ref={ref} className="cursor-field" aria-hidden="true" />;
}
