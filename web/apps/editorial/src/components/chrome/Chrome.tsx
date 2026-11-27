"use client";

import { useEffect, useState } from "react";
import { CHAPTERS, REPO } from "@/content/story";
import { useMotion } from "@/lib/motion";

/* Masthead with the chapter index folded into it: one dropdown instead of a bar across the page. */
export function Masthead() {
  const { on, ready, toggle } = useMotion();
  const [current, setCurrent] = useState(0);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => entries.forEach((e) => e.isIntersecting && setCurrent(Number((e.target as HTMLElement).dataset.chapter))),
      { rootMargin: "-50% 0px -50% 0px" },
    );
    document.querySelectorAll("[data-chapter]").forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);

  return (
    <header className="masthead">
      <a href="#collision" className="brand">
        <img src="/mark.svg" alt="" width="26" height="26" />
        InterviewOps
      </a>
      <div className="index">
        <button type="button" aria-expanded={open} aria-controls="chapter-list" onClick={() => setOpen(!open)}>
          <span className="num">{String(current).padStart(2, "0")}</span>
          <span className="name">{CHAPTERS[current].short}</span>
          <span className="of">/ 09</span>
        </button>
        <ol id="chapter-list" hidden={!open}>
          {CHAPTERS.map((c, i) => (
            <li key={c.id}>
              <a href={`#${c.id}`} aria-current={i === current ? "step" : undefined} onClick={() => setOpen(false)}>
                <span>{String(i).padStart(2, "0")}</span>
                {c.short}
              </a>
            </li>
          ))}
        </ol>
      </div>
      <nav aria-label="Site">
        <a href={REPO}>GitHub</a>
        <button type="button" onClick={toggle} aria-pressed={on} disabled={!ready}>
          Motion {on ? "on" : "off"}
        </button>
      </nav>
    </header>
  );
}
