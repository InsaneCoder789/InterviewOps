"use client";

import { animate, stagger } from "animejs";
import { useEffect, useRef, useState } from "react";
import { CHAPTERS } from "@/content/story";
import { useMotion } from "@/lib/motion";
import { story, type Role } from "@/lib/store";
import { Chapter } from "../motion/Chapter";
import { Rich, Sources, Still, Title } from "../motion/primitives";

const ROWS = [
  { time: "09:00", topic: "System design", mentor: "mentor-1", student: "student-1" },
  { time: "10:00", topic: "Algorithms", mentor: "mentor-1", student: null },
  { time: "11:00", topic: "Behavioural", mentor: "mentor-2", student: "student-2" },
  { time: "14:00", topic: "Databases", mentor: "mentor-2", student: "student-1" },
];

/* What one viewer gets back. The viewer is student-1, mentor-1, or an admin. */
function view(role: Role, row: (typeof ROWS)[number]) {
  if (role === "admin") return { slot: true, booking: row.student ? `booked by ${row.student}` : "open" };
  if (role === "mentor") return row.mentor === "mentor-1" ? { slot: true, booking: row.student ? `booked by ${row.student}` : "open" } : { slot: false, booking: "404" };
  return { slot: true, booking: row.student === "student-1" ? "your booking" : row.student ? "taken" : "open" };
}

export function Access() {
  const copy = CHAPTERS[7];
  const [role, setRole] = useState<Role>("student");
  const list = useRef<HTMLUListElement>(null);
  const { on } = useMotion();

  useEffect(() => {
    if (!on || !list.current) return;
    const flip = animate(list.current.querySelectorAll("li"), { translateX: [24, 0], opacity: [0.2, 1], delay: stagger(60), duration: 520, ease: "out(4)" });
    return () => void flip.revert();
  }, [role, on]);

  return (
    <Chapter index={7} className="access">
      <div className="column">
        <Title index={7} />
        {copy.body.map((text, i) => <p key={i}><Rich text={text} /></p>)}
        <Sources items={copy.sources} />
      </div>
      <div className="panel">
        <fieldset>
          <legend>View the same morning as</legend>
          {(["student", "mentor", "admin"] as Role[]).map((r) => (
            <label key={r}>
              <input type="radio" name="role" value={r} checked={role === r} onChange={() => { story.role = r; setRole(r); }} />
              <span>{r === "student" ? "student-1" : r === "mentor" ? "mentor-1" : "admin"}</span>
            </label>
          ))}
        </fieldset>
        <ul ref={list} aria-live="polite">
          {ROWS.map((row) => {
            const seen = view(role, row);
            return (
              <li key={row.time} data-hidden={!seen.slot || undefined}>
                <time>{row.time}</time>
                <span>{seen.slot ? `${row.topic}, ${row.mentor}` : "Not found, or not visible to you"}</span>
                <b>{seen.booking}</b>
              </li>
            );
          })}
        </ul>
        <p className="note">Made-up accounts and sessions, to illustrate the rules.</p>
      </div>
      <Still name="ch7-1-student" alt="The slot list as a student sees it." />
    </Chapter>
  );
}
