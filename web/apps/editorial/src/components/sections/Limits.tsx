"use client";

import { CHAPTERS, LIMITS } from "@/content/story";
import { Chapter } from "../motion/Chapter";
import { Reveal, Sources, Title } from "../motion/primitives";

export function Limits() {
  const copy = CHAPTERS[8];
  return (
    <Chapter index={8} tone="day" className="limits">
      <Title index={8} className="title-wide" />
      <p className="lead">{copy.body[0]}</p>
      <ul>
        {LIMITS.map((limit, i) => (
          <li key={limit.head}>
            <Reveal delay={i * 80} className="limit">
              <h3>{limit.head}</h3>
              <p>{limit.text}</p>
            </Reveal>
          </li>
        ))}
      </ul>
      <Sources items={copy.sources} />
    </Chapter>
  );
}
