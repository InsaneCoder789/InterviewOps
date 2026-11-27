"use client";

import { CHAPTERS } from "@/content/story";
import { Chapter } from "../motion/Chapter";
import { Reveal, ScrubText, Sources, Title } from "../motion/primitives";

/* The first daylight interlude: no 3D, only type. The scene stops while this page covers it. */
export function Why() {
  const copy = CHAPTERS[1];
  return (
    <Chapter index={1} tone="day" className="essay">
      <Title index={1} className="title-wide" />
      <div className="essay-grid">
        <ScrubText text={copy.body[0]} className="essay-big" />
        <div className="essay-side">
          <Reveal><p>{copy.body[1]}</p></Reveal>
          <Reveal delay={120}><p>{copy.body[2]}</p></Reveal>
          <Sources items={copy.sources} />
        </div>
      </div>
      {/* two people, one interval: the blocks close in on each other as the page is read */}
      <div className="meet" aria-hidden="true"><i /><i /></div>
    </Chapter>
  );
}
