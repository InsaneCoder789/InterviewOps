"use client";

import { useState } from "react";
import { CHAPTERS, CONSTRAINTS } from "@/content/story";
import { story } from "@/lib/store";
import { Chapter } from "../motion/Chapter";
import { Sources, Steps, Still, Title } from "../motion/primitives";

const DAY_START = 8;
const DAY_END = 13;
const HELD = { from: 10, to: 11 };
const clock = (h: number) => `${String(Math.floor(h)).padStart(2, "0")}:${String(Math.round((h % 1) * 60)).padStart(2, "0")}`;
const at = (h: number) => `${((h - DAY_START) / (DAY_END - DAY_START)) * 100}%`;

/* The reader moves a second booking along a student's morning. Half-open comparison: [start, end). */
export function TimeTrack() {
  const [from, setFrom] = useState(story.attempt);
  const to = from + 1;
  const overlaps = from < HELD.to && HELD.from < to;
  return (
    <div className="timetrack" data-refused={overlaps || undefined}>
      <label htmlFor="attempt">Move a second booking for the same student</label>
      <div className="lanes">
        <div className="lane">
          <span className="block held" style={{ left: at(HELD.from), width: "20%" }}>10:00 to 11:00, held</span>
        </div>
        <div className="lane">
          <span className="block try" style={{ left: at(from), width: "20%" }}>{clock(from)} to {clock(to)}</span>
        </div>
        <div className="axis" aria-hidden="true">{[8, 9, 10, 11, 12, 13].map((h) => <span key={h} style={{ left: at(h) }}>{clock(h)}</span>)}</div>
      </div>
      <input
        id="attempt"
        type="range"
        min={DAY_START}
        max={DAY_END - 1}
        step={0.25}
        value={from}
        aria-valuetext={`${clock(from)} to ${clock(to)}`}
        onChange={(event) => {
          const next = Number(event.target.value);
          story.attempt = next;
          setFrom(next);
        }}
      />
      <output htmlFor="attempt" aria-live="polite">
        <b>{overlaps ? "409 Conflict" : "Accepted"}</b>
        <span>
          {overlaps
            ? "You already have a booking at this time."
            : from === HELD.to || to === HELD.from
              ? "The two sessions touch. Half-open ranges do not collide."
              : "No overlap with the held session."}
        </span>
      </output>
      <p className="note">Illustration of the overlap rule. Nothing is sent to a server.</p>
    </div>
  );
}

export function Constraints() {
  const copy = CHAPTERS[4];
  return (
    <Chapter index={4} length={4.2} steps={copy.body.length} className="split instrument">
      {(step) => (
        <>
          <div className="column">
            <Title index={4} />
            <Steps paragraphs={copy.body} step={step} />
            <Sources items={copy.sources} />
          </div>
          <div className="panel">
            <TimeTrack />
            <table>
              <caption>The three constraints</caption>
              <thead><tr><th scope="col">Constraint</th><th scope="col">Kind</th><th scope="col">Rule</th></tr></thead>
              <tbody>
                {CONSTRAINTS.map((c) => (
                  <tr key={c.name}><th scope="row"><code>{c.name}</code></th><td>{c.kind}</td><td>{c.rule}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <Still name="ch4-2-overlap-refused" alt="The database refuses an overlapping booking." />
        </>
      )}
    </Chapter>
  );
}
