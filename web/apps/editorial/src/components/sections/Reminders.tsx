"use client";

import { CHAPTERS, RETRY_WAITS } from "@/content/story";
import { Chapter } from "../motion/Chapter";
import { Sources, Steps, Still, Title } from "../motion/primitives";

const TOTAL = RETRY_WAITS.reduce((a, b) => a + b, 0);

/* Ten attempts placed on a line at their true spacing. The fill follows the scroll. */
function RetryScale() {
  let elapsed = 0;
  const marks = [0, ...RETRY_WAITS.map((wait) => (elapsed += wait))];
  return (
    <figure className="retry">
      <figcaption>Ten attempts, drawn to scale over {TOTAL} minutes</figcaption>
      <div className="retry-line" aria-hidden="true">
        <i className="retry-fill" />
        {marks.map((minute, i) => (
          <span key={i} style={{ left: `${(minute / TOTAL) * 100}%` }} data-last={i === marks.length - 1 || undefined} data-low={i % 2 === 1 || undefined}>
            <b>{i + 1}</b>
          </span>
        ))}
      </div>
      <p>Waits in minutes: {RETRY_WAITS.join(", ")}. After the tenth failure the reminder is marked failed.</p>
    </figure>
  );
}

export function Reminders() {
  const copy = CHAPTERS[6];
  return (
    <Chapter index={6} length={4.2} steps={copy.body.length} className="queue">
      {(step) => (
        <>
          <div className="queue-top">
            <Title index={6} />
            <Steps paragraphs={copy.body} step={step} />
          </div>
          <RetryScale />
          <Sources items={copy.sources} />
          <Still name="ch6-2-retries" alt="Retry attempts spaced further apart each time." />
        </>
      )}
    </Chapter>
  );
}
