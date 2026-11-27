"use client";

import { CHAPTERS, DEADLOCK_RUN } from "@/content/story";
import { Chapter } from "../motion/Chapter";
import { Sources, Steps, Still, Title } from "../motion/primitives";

export function Deadlock() {
  const copy = CHAPTERS[5];
  return (
    <Chapter index={5} length={4.8} steps={copy.body.length} className="deadlock">
      {(step) => (
        <>
          <Title index={5} />
          <div className="deadlock-copy">
            <Steps paragraphs={copy.body} step={step} />
            <Sources items={copy.sources} />
          </div>
          <figure className="tally" data-on={step < 0 || step >= 2 || undefined}>
            <figcaption>30 rounds, two requests each, lock removed</figcaption>
            <ul>
              {DEADLOCK_RUN.map((row) => (
                <li key={row.label} data-tone={row.tone} style={{ ["--share" as string]: row.count / 30 }}>
                  <b>{row.count}</b>
                  <span>{row.label}</span>
                  <i aria-hidden="true" />
                </li>
              ))}
            </ul>
            <p>Counts vary between runs. This was a local test with a lock taken out on purpose. It never happened to a deployed system, because there is none.</p>
          </figure>
          <Still name="ch5-4-loop" alt="Two requests, each waiting for the other." />
        </>
      )}
    </Chapter>
  );
}
