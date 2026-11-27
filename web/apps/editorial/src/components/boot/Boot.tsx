"use client";

import { createTimer } from "animejs";
import { useEffect, useRef, useState } from "react";
import { useMotion } from "@/lib/motion";
import { BOOT_END, story } from "@/lib/store";

export const BOOT_KEY = "io-boot";

/* The caption track of the film: [second it appears, request, line, tone]. Illustrative, matching chapter 3. */
const LINES: Array<[number, string, string, string]> = [
  [0.5, "A", "asks for the 10:00 slot", "a"],
  [0.85, "B", "asks for the 10:00 slot", "b"],
  [2.75, "A", "locks the slot row", "waiting"],
  [3.15, "B", "waits", "waiting"],
  [3.9, "A", "201 Created", "booked"],
  [4.55, "B", "409 This slot is already booked.", "conflict"],
];
const REVEAL_AT = 5.2;

/*
 * The opening: the first shot of the same take the page continues. The 3D slot station performs it (story.boot is its
 * only input); this overlay adds the caption track and a clock, then opens from a closed start bar toward the open end.
 * Plays once per tab. Skip with the button, Escape or Enter. Never plays with motion off or without WebGL.
 * Development only: ?bootSeek=3.2 holds one moment.
 */
export function Boot() {
  const { on, ready } = useMotion();
  const [phase, setPhase] = useState<"pending" | "running" | "gone">("pending");
  const [count, setCount] = useState(0);
  const clockRef = useRef<HTMLSpanElement>(null);
  const skipRef = useRef<() => void>(() => {});

  useEffect(() => {
    if (!ready) return;
    const html = document.documentElement;
    if (!on || html.dataset.boot !== "running") {
      html.dataset.boot = "done";
      story.boot = BOOT_END;
      setPhase("gone");
      return;
    }

    const seekText = process.env.NODE_ENV !== "production" ? new URLSearchParams(location.search).get("bootSeek") : null;
    const seek = seekText === null ? null : Number(seekText);
    story.boot = 0;
    window.scrollTo(0, 0);

    // while the film plays, the page behind it is out of reach of keyboard and screen reader
    const behind = Array.from(document.querySelectorAll<HTMLElement>("[data-page]"));
    behind.forEach((el) => (el.inert = true));

    let timer: ReturnType<typeof createTimer> | null = null;
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      timer?.pause();
      story.boot = BOOT_END;
      html.dataset.boot = "done";
      behind.forEach((el) => (el.inert = false));
      try { sessionStorage.setItem(BOOT_KEY, "1"); } catch {}
      setPhase("gone");
    };
    const show = (t: number) => {
      story.boot = Math.min(t, BOOT_END);
      setCount(LINES.filter(([at]) => t >= at).length);
      if (clockRef.current) clockRef.current.textContent = t.toFixed(3);
      if (t >= REVEAL_AT) html.dataset.boot = "reveal";
    };

    let offset = 0;
    const start = () => {
      if (timer || finished) return;
      setPhase("running");
      if (seek !== null && Number.isFinite(seek)) return show(seek);
      timer = createTimer({
        duration: BOOT_END * 1000,
        onUpdate: (self) => {
          const t = self.currentTime / 1000 + offset;
          if (t >= BOOT_END) finish();
          else show(t);
        },
        onComplete: finish,
      });
    };
    // skipping jumps to the opening wipe, so the site still arrives through the slot
    skipRef.current = () => {
      if (!timer) return finish();
      if (story.boot < REVEAL_AT) offset += REVEAL_AT - story.boot;
    };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape" || e.key === "Enter") skipRef.current(); };

    window.addEventListener("keydown", key);
    window.addEventListener("world:ready", start, { once: true });
    window.addEventListener("world:failed", finish, { once: true });
    const late = window.setTimeout(start, 4500); // normally the canvas says it is ready well before this
    const failsafe = seek === null ? window.setTimeout(finish, (BOOT_END + 8) * 1000) : 0;

    return () => {
      window.clearTimeout(late);
      window.clearTimeout(failsafe);
      window.removeEventListener("keydown", key);
      window.removeEventListener("world:ready", start);
      window.removeEventListener("world:failed", finish);
      timer?.pause();
      behind.forEach((el) => (el.inert = false));
    };
  }, [on, ready]);

  if (phase === "gone") return null;

  return (
    <div className="boot" role="region" aria-label="Opening animation">
      <div className="boot-bar" aria-hidden="true" />
      <p className="boot-name" aria-hidden="true">InterviewOps</p>
      <ol className="boot-log" aria-hidden="true">
        {LINES.slice(0, count).map(([at, who, line, tone]) => (
          <li key={at} data-tone={tone}><b>{who}</b>{line}</li>
        ))}
      </ol>
      <p className="boot-clock" aria-hidden="true"><span ref={clockRef}>0.000</span><small>seconds, illustrative</small></p>
      <button type="button" className="boot-skip" onClick={() => skipRef.current()}>Skip intro</button>
    </div>
  );
}
