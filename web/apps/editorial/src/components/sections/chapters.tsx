"use client";

import { CHAPTERS, REPO } from "@/content/story";
import { Chapter } from "../motion/Chapter";
import { Reveal, Rich, Sources, Steps, Still, Title } from "../motion/primitives";

/* Chapters 0, 2, 3 and 9. Chapters with their own instruments live in separate files. */

export function Hero() {
  const copy = CHAPTERS[0];
  return (
    <Chapter index={0} length={2.2} className="hero">
      <div className="hero-copy">
        <Title index={0} as="h1" className="title-hero" />
        <p className="lead">{copy.body[0]}</p>
        <div className="actions">
          <a className="button primary" href="#anatomy">See how it works</a>
          <a className="button" href={REPO}>Read the code</a>
        </div>
      </div>
      <div className="hero-more">
        <p><Rich text={copy.body[1]} /></p>
        <p>{copy.body[2]}</p>
        <Sources items={copy.sources} />
      </div>
      <Still name="ch0-2-result" alt="Illustration: one request is booked and the other receives a conflict." />
    </Chapter>
  );
}

const LOG = [
  { who: "A", text: "is the slot free?", answer: "yes" },
  { who: "B", text: "is the slot free?", answer: "yes" },
  { who: "A", text: "insert booking", answer: "ok" },
  { who: "B", text: "insert booking", answer: "ok" },
];

export function Anatomy() {
  const copy = CHAPTERS[2];
  return (
    <Chapter index={2} length={4.2} steps={copy.body.length} className="split">
      {(step) => (
        <>
          <div className="column">
            <Title index={2} />
            <Steps paragraphs={copy.body} step={step} />
            <Sources items={copy.sources} />
          </div>
          <ol className="log" aria-label="Order of events, an illustration of the mistake">
            {LOG.map((row, i) => (
              <li key={i} data-who={row.who} data-on={step < 0 || i <= step || undefined}>
                <b>request {row.who}</b>
                <span>{row.text}</span>
                <em>{row.answer}</em>
              </li>
            ))}
          </ol>
          <Still name="ch2-4-two-bookings" alt="Hypothetical sequence ending in two bookings for one slot." />
        </>
      )}
    </Chapter>
  );
}

const ORDER = [
  { name: "Student row", lock: "FOR NO KEY UPDATE" },
  { name: "Slot row", lock: "FOR NO KEY UPDATE" },
  { name: "Rules", lock: "checked after the wait" },
  { name: "Write", lock: "booking and its email, one commit" },
];

/* Four stages of one transaction, taken in a fixed order. The current stage is lit; the caption explains it. */
export function Locks() {
  const copy = CHAPTERS[3];
  return (
    <Chapter index={3} length={4.2} steps={4} className="split">
      {(step) => (
        <>
          <div className="column">
            <Title index={3} />
            <Steps paragraphs={copy.body} step={step} />
            <Sources items={copy.sources} />
          </div>
          <ol className="stages" aria-label="Lock order inside one booking">
            {ORDER.map((stage, i) => (
              <li key={stage.name} data-state={step < 0 ? "on" : i < step ? "past" : i === step ? "on" : "next"}>
                <span className="n">{i + 1}</span>
                <strong>{stage.name}</strong>
                <code>{stage.lock}</code>
              </li>
            ))}
          </ol>
          <Still name="ch3-3-b-waits" alt="Request B waits for the slot lock held by request A." />
        </>
      )}
    </Chapter>
  );
}

export function Enter() {
  const copy = CHAPTERS[9];
  return (
    <Chapter index={9} className="enter">
      <Title index={9} className="title-hero" />
      <Reveal className="enter-body">
        <p className="lead">{copy.body[0]}</p>
        <pre aria-label="Commands to run InterviewOps with Docker"><code>{`git clone ${REPO}.git\ncd InterviewOps\ndocker compose up --build`}</code></pre>
        <div className="actions">
          <a className="button primary" href={`${REPO}#quickstart`}>Run it locally</a>
          <a className="button" href={REPO}>Read the code</a>
        </div>
        <Sources items={copy.sources} />
      </Reveal>
      <Still name="ch9-1-day-track" alt="Illustrative day of booked and open slots." />
    </Chapter>
  );
}
