/*
 * The one clock. Scroll writes here; the 3D world reads it every frame without re-rendering React.
 * Everything the camera and the stations do is a pure function of these numbers, so scrolling back undoes it exactly.
 */

export const CHAPTER_COUNT = 10;
export const BOOT_END = 6.4; // seconds

export type Role = "student" | "mentor" | "admin";

export const story = {
  arrive: new Array<number>(CHAPTER_COUNT).fill(0), // 0..1 while a chapter slides in
  progress: new Array<number>(CHAPTER_COUNT).fill(0), // 0..1 while a chapter is pinned or being read
  boot: BOOT_END, // current time of the opening film; BOOT_END means finished
  role: "student" as Role,
  attempt: 9.5, // chapter 4: requested start hour of the second booking
  pointer: { x: 0, y: 0 }, // -1..1
};

/** Continuous camera position in chapters: 2.5 is halfway between chapter 2 and 3. */
export const cameraPosition = () => story.arrive.reduce((sum, value, i) => (i === 0 ? sum : sum + smooth(value)), 0);

export const clamp = (v: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v));
export const smooth = (v: number) => {
  const k = clamp(v);
  return k * k * (3 - 2 * k);
};
/** 0 before `from`, 1 after `to`, eased between. */
export const span = (v: number, from: number, to: number) => smooth((v - from) / (to - from));

export const lerpIn = (a: number, b: number, k: number) => a + (b - a) * k;
