"use client";

import { animate, onScroll, splitText, stagger } from "animejs";
import { useEffect, useRef, type ElementType, type ReactNode } from "react";
import { CHAPTERS, type Source } from "@/content/story";
import { useMotion } from "@/lib/motion";
import { Still } from "./Still";

/** Chapter title. Words rise out of a mask, line by line, when the title enters the screen. */
export function Title({ index, as: Tag = "h2", className = "" }: { index: number; as?: ElementType; className?: string }) {
  const ref = useRef<HTMLElement>(null);
  const { on } = useMotion();
  const copy = CHAPTERS[index];

  useEffect(() => {
    const el = ref.current;
    if (!el || !on) return;
    // one splitter per line: splitText reads a single element
    const splits = Array.from(el.querySelectorAll<HTMLElement>(".line"), (line) => splitText(line, { words: { wrap: "clip" }, accessible: false }));
    const rise = animate(splits.flatMap((s) => s.words), {
      translateY: ["115%", "0%"],
      rotate: [4, 0],
      duration: 1100,
      delay: stagger(70),
      ease: "out(4)",
      autoplay: false,
    });
    // an observer, not a scroll trigger: titles inside sticky stages never cross a scroll threshold
    const seen = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      rise.play();
      seen.disconnect();
    }, { threshold: 0.2 });
    seen.observe(el);
    return () => {
      seen.disconnect();
      rise.revert();
      splits.forEach((s) => s.revert());
    };
  }, [on]);

  return (
    <Tag ref={ref} id={`${copy.id}-title`} className={`title ${className}`} aria-label={copy.title.join(" ")}>
      {copy.title.map((line) => (
        <span className="line" aria-hidden="true" key={`${on}-${line}`}>
          {line}{" "}
        </span>
      ))}
    </Tag>
  );
}

/** Fades and lifts its children the first time they enter the screen. */
export function Reveal({ children, className = "", delay = 0 }: { children: ReactNode; className?: string; delay?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const { on } = useMotion();
  useEffect(() => {
    const el = ref.current;
    if (!el || !on) return;
    const animation = animate(el, {
      opacity: [0, 1],
      translateY: [36, 0],
      duration: 900,
      delay,
      ease: "out(3)",
      autoplay: onScroll({ target: el, enter: "end-=6% start" }),
    });
    return () => void animation.revert();
  }, [on, delay]);
  return <div ref={ref} className={className}>{children}</div>;
}

/** A paragraph whose words light up in step with scrolling. */
export function ScrubText({ text, className = "" }: { text: string; className?: string }) {
  const ref = useRef<HTMLParagraphElement>(null);
  const { on } = useMotion();
  useEffect(() => {
    const el = ref.current;
    if (!el || !on) return;
    const split = splitText(el, { words: true, accessible: false });
    const light = animate(split.words, {
      opacity: [0.16, 1],
      duration: 400,
      delay: stagger(60),
      ease: "linear",
      autoplay: onScroll({ target: el, enter: "end-=12% start", leave: "center+=5% end", sync: 0.4 }),
    });
    return () => {
      light.revert();
      split.revert();
    };
  }, [on]);
  return (
    <p ref={ref} className={className} key={String(on)}>
      <Rich text={text} />
    </p>
  );
}

/** Renders [label](url) links and `code` inside story copy. */
export function Rich({ text }: { text: string }) {
  return text.split(/(\[[^\]]+\]\([^)]+\)|`[^`]+`)/g).map((part, i) => {
    const link = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (link) return <a key={i} className="cite" href={link[2]}>{link[1]}</a>;
    if (part.startsWith("`")) return <code key={i}>{part.slice(1, -1)}</code>;
    return part;
  });
}

export function Sources({ items }: { items: Source[] }) {
  return (
    <div className="sources">
      <h3>Sources</h3>
      <ul>
        {items.map((s) => (
          <li key={s.href}><a href={s.href}>{s.label}</a></li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Caption stack for a pinned stage. Every paragraph stays in the document; the one for the current step is shown.
 * With motion off (step -1) they are all shown as ordinary prose.
 */
export function Steps({ paragraphs, step }: { paragraphs: string[]; step: number }) {
  return (
    <div className="steps">
      <div className="steps-stack">
        {paragraphs.map((text, i) => (
          <p key={i} data-state={step < 0 || i === step ? "on" : i < step ? "past" : "next"}>
            <Rich text={text} />
          </p>
        ))}
      </div>
      {step >= 0 && <StepBar count={paragraphs.length} step={step} />}
    </div>
  );
}

function StepBar({ count, step }: { count: number; step: number }) {
  const go = (to: number) => (event: React.MouseEvent) => {
    const section = event.currentTarget.closest("section");
    if (!section) return;
    const top = section.getBoundingClientRect().top + window.scrollY;
    const travel = section.offsetHeight - window.innerHeight;
    window.scrollTo({ top: top + travel * ((to + 0.6) / count), behavior: "smooth" });
  };
  return (
    <div className="stepbar">
      <button type="button" onClick={go(Math.max(0, step - 1))} disabled={step === 0}>Previous step</button>
      <span className="ticks" aria-label={`Step ${step + 1} of ${count}`} role="img">
        {Array.from({ length: count }, (_, i) => <i key={i} data-on={i <= step || undefined} />)}
      </span>
      <button type="button" onClick={go(Math.min(count - 1, step + 1))} disabled={step === count - 1}>Next step</button>
    </div>
  );
}

export { Still };
