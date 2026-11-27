"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { CHAPTERS } from "@/content/story";
import { useMotion } from "@/lib/motion";
import { watchScroll } from "@/lib/scroll";
import { clamp, story } from "@/lib/store";

type Props = {
  index: number;
  tone?: "night" | "day";
  /** Viewport heights of scroll while pinned. 1 means not pinned. */
  length?: number;
  /** Number of caption steps inside the pinned stage. */
  steps?: number;
  className?: string;
  children: ReactNode | ((step: number) => ReactNode);
};

/*
 * The base of every chapter. Two numbers per section feed the story clock:
 *   arrive    section top travels from the bottom of the viewport to the top (drives the camera between stations)
 *   progress  section is held (pinned) or read through (drives the station and the captions)
 * They are measured from the section's position, not accumulated from events, so a jump from the chapter rail lands in
 * exactly the same state as scrolling there.
 */
export function Chapter({ index, tone = "night", length = 1, steps = 1, className = "", children }: Props) {
  const ref = useRef<HTMLElement>(null);
  const { on } = useMotion();
  const [step, setStep] = useState(0);
  const pinned = length > 1;

  useEffect(() => {
    const section = ref.current;
    if (!section || !on) return;
    return watchScroll(() => {
      const box = section.getBoundingClientRect();
      const view = window.innerHeight;
      const arrive = clamp((view - box.top) / view);
      const progress = pinned ? clamp(-box.top / Math.max(1, box.height - view)) : 0;
      if (arrive === story.arrive[index] && progress === story.progress[index]) return;
      story.arrive[index] = arrive;
      story.progress[index] = progress;
      section.style.setProperty("--arrive", arrive.toFixed(4));
      section.style.setProperty("--progress", progress.toFixed(4));
      setStep(Math.min(steps - 1, Math.floor(progress * steps)));
    });
  }, [on, index, steps, pinned]);

  const copy = CHAPTERS[index];
  return (
    <section
      ref={ref}
      id={copy.id}
      data-chapter={index}
      data-step={step}
      data-pinned={pinned || undefined}
      className={`chapter ${tone} ${className}`}
      style={{ ["--length" as string]: length }}
      aria-labelledby={`${copy.id}-title`}
    >
      <div className="stage">{typeof children === "function" ? children(on ? step : -1) : children}</div>
    </section>
  );
}
