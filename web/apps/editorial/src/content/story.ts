/*
 * All story copy. The words are the owner-approved text from docs/plan/STORY.md (with the later corrections that the
 * previous page already carried). Change copy here, never inside components, and check it against the code first.
 */

export const REPO = "https://github.com/InsaneCoder789/InterviewOps";
const file = (path: string) => ({ label: path, href: `${REPO}/blob/main/${path}` });

export type Source = { label: string; href: string };
export type ChapterCopy = {
  id: string;
  short: string;
  title: string[]; // one entry per display line: lines break by meaning
  body: string[]; // [label](url) and `code` are rendered by <Rich />
  sources: Source[];
};

export const CHAPTERS: ChapterCopy[] = [
  {
    id: "collision",
    short: "Two requests",
    title: ["Two requests.", "One slot."],
    body: [
      "A mentor offers one hour. Two students ask for it at the same moment.",
      "One of them should get a booking. The other should get a clear answer, at once, that the hour is taken. There is no third acceptable outcome: not two bookings, and not a server error.",
      "InterviewOps is a small backend for scheduling mock interviews, built around that moment.",
    ],
    sources: [file("scheduling/services.py"), file("tests/test_concurrency.py")],
  },
  {
    id: "why",
    short: "Why it matters",
    title: ["Practice has to be", "on the calendar."],
    body: [
      "Being interviewed is its own skill, with its own pressure. In a 2020 study of 48 computer science students, those who solved a problem while an interviewer watched did about half as well as those who worked alone. [NC State](https://news.ncsu.edu/?p=509799) The study did not test practice sessions. It does show that solving a problem and solving it in front of someone are different tasks.",
      "A mock interview is a way to meet the second task early. It needs two people in the same hour. If the booking is wrong, someone prepares for a session that will not happen.",
      "There are no figures here on how often scheduling tools get this wrong, and none are guessed. None are needed to see how it can happen.",
    ],
    sources: [{ label: "NC State news on an FSE 2020 study", href: "https://news.ncsu.edu/?p=509799" }, file("scheduling/models.py")],
  },
  {
    id: "anatomy",
    short: "The collision",
    title: ["Both looked.", "Both saw it free."],
    body: [
      "The obvious way to book a slot is two steps. Check that no booking exists. Then insert one.",
      "Neither request is wrong about what it read. PostgreSQL, at its default isolation level, shows a query only what was committed before the query began. [PostgreSQL](https://www.postgresql.org/docs/current/transaction-iso.html)",
      "A booking still in progress is invisible. With nothing else in the way, both inserts succeed.",
      "This sequence is an illustration of the mistake, not code from InterviewOps. The rest of this story is about what stands in its way.",
    ],
    sources: [
      { label: "PostgreSQL: transaction isolation", href: "https://www.postgresql.org/docs/current/transaction-iso.html" },
      file("scheduling/services.py"),
      file("scheduling/models.py"),
    ],
  },
  {
    id: "locks",
    short: "Ordered locks",
    title: ["Wait your turn,", "in a fixed order."],
    body: [
      "Every booking runs inside one transaction. It locks the student's row, then the slot's row, then checks the rules, then writes.",
      "Two students after one slot hold different student locks, so they pass the first step side by side. They meet at the slot. One locks it. The other waits, and when its turn comes it finds the booking and receives `409 Conflict`: \"This slot is already booked.\"",
      "Order matters as much as locking. Operations take user rows first, then the slot, then the booking, so that two of them are not left each holding what the other needs.",
      "The rules are checked after the wait. The clock is read after the wait too, so a request that queued while the session began cannot book it.",
    ],
    sources: [file("scheduling/services.py"), file("docs/ARCHITECTURE.md")],
  },
  {
    id: "constraints",
    short: "The database",
    title: ["Skip the queue.", "The database still refuses."],
    body: [
      "Suppose some other code writes a booking directly and takes no locks at all. The tables carry their own rules.",
      "A slot may have one active booking. A student's active bookings may not overlap. A mentor's active slots may not overlap. PostgreSQL enforces these on every write. When a request through the service trips one, the answer is a `409` with a sentence saying why.",
      "Sessions are measured as half-open intervals. One that ends at 10:00 and one that begins at 10:00 touch without colliding.",
      "The database does not know every rule. Whether a slot has been cancelled or has started, and who is allowed to book, are decided in the service. The student overlap rule compares times copied from the slot onto the booking; the database checks that those times match.",
    ],
    sources: [
      file("scheduling/models.py"),
      file("scheduling/migrations/0001_btree_gist.py"),
      file("tests/test_database_rules.py"),
      { label: "PostgreSQL: constraints", href: "https://www.postgresql.org/docs/current/ddl-constraints.html" },
    ],
  },
  {
    id: "deadlock",
    short: "Deadlock",
    title: ["One lock removed.", "Two requests froze each other."],
    body: [
      "Turn the opening around. One student sends two requests at once, for two different slots at the same hour. One should succeed. The other should be refused.",
      "During testing the student lock was deliberately removed. The two requests lock different slots, so nothing else put them in order. Each inserted its booking, then went to check for overlap, found the other's uncommitted row and waited for it. Each was waiting for the other.",
      "PostgreSQL detects this and aborts one transaction. [PostgreSQL](https://www.postgresql.org/docs/current/explicit-locking.html) In this code that surfaced as an unhandled database error, which the API would return as a `500`.",
      "The constraint kept the data correct throughout. The lock is what makes the refusal orderly. Putting it back means one student's bookings run one at a time, and the second request sees a finished result.",
    ],
    sources: [
      file("docs/investigation-001-deadlock.md"),
      file("tests/test_concurrency.py"),
      { label: "PostgreSQL: explicit locking", href: "https://www.postgresql.org/docs/current/explicit-locking.html" },
    ],
  },
  {
    id: "reminders",
    short: "Reminders",
    title: ["Written with the booking.", "Retried until sent, within limits."],
    body: [
      "A booking queues its emails in the same transaction: a confirmation and a reminder for the student and for the mentor. The booking and its messages are saved together or not at all. Changes and cancellations use the same queue.",
      "A separate worker picks up reminders that are due, 24 hours before the session, or straight away for a later booking. It claims one, skipping any that another worker holds, and leases it for five minutes. The email is sent outside the transaction, so a slow mail server holds no database locks.",
      "If sending fails, the worker waits one minute, then two, then four, up to an hour between tries. After ten attempts, about four hours, it marks the reminder failed. If a worker dies mid-send, the lease expires and the reminder is claimed again.",
      "The price of that persistence: a reminder can arrive twice. If the mail server accepts a message and the worker dies before recording it, the message is sent again. A cancellation made during the send cannot call the email back.",
    ],
    sources: [
      file("notifications/delivery.py"),
      file("config/settings.py"),
      file("tests/test_notifications.py"),
      { label: "PostgreSQL: SELECT", href: "https://www.postgresql.org/docs/current/sql-select.html" },
    ],
  },
  {
    id: "access",
    short: "Who sees what",
    title: ["If it is not yours,", "it is not there."],
    body: [
      "Students see upcoming slots from active mentors, including whether each is taken, but not by whom. Mentors see their own slots and the bookings on them. Admins see everything.",
      "Ask for someone else's booking and the answer is `404 Not Found`, the same as for a booking that never existed. The standard allows this when a server would rather not confirm that something is there. [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html)",
      "Roles are not self-declared. People join by invitation with the role an admin chose; where open sign-up is enabled, it creates a student. Only an admin changes a role, not their own, and not while that person has sessions still to come. Two admins who try to demote each other at the same moment cannot both succeed.",
    ],
    sources: [file("scheduling/views.py"), file("accounts/permissions.py"), file("scheduling/services.py")],
  },
  {
    id: "limits",
    short: "What is missing",
    title: ["What is missing."],
    body: [
      "InterviewOps runs on a developer's machine. It has not been deployed, it has no users, and nothing about its speed or capacity has been measured. A container file and a hosting blueprint are included; nothing has been deployed from them.",
    ],
    sources: [file("README.md"), file("SECURITY.md")],
  },
  {
    id: "enter",
    short: "Take a slot",
    title: ["Take a slot."],
    body: ["The backend runs on your own machine against your own database. There is no web app yet and no hosted instance."],
    sources: [file("accounts/urls.py"), file("scheduling/urls.py"), file("README.md")],
  },
];

export const LIMITS = [
  { head: "Accounts", text: "Public sign-up is closed unless the operator opens it; people join by invitation. Each account has one sign-in token." },
  { head: "Scheduling", text: "No editing a slot or repeating availability. Some rules are enforced by the application only, not by the database." },
  { head: "Email", text: "Plain text, with times in UTC. A message can be repeated." },
  { head: "Beyond booking", text: "No calendar sync, hosted video, matching or payments." },
];

export const CONSTRAINTS = [
  { name: "booking_one_active_per_slot", kind: "partial unique index", rule: "A slot has at most one active booking." },
  { name: "booking_no_student_overlap", kind: "exclusion", rule: "A student's active bookings do not overlap." },
  { name: "slot_no_mentor_overlap", kind: "exclusion", rule: "A mentor's active slots do not overlap." },
];

/** Minutes waited between the ten attempts: doubles from 1, capped at 60 (config/settings.py). */
export const RETRY_WAITS = [1, 2, 4, 8, 16, 32, 60, 60, 60];

/** Recorded in docs/investigation-001-deadlock.md. */
export const DEADLOCK_RUN = [
  { label: "Booking created", count: 30, tone: "booked" },
  { label: "Clean conflict", count: 27, tone: "waiting" },
  { label: "Deadlock", count: 3, tone: "conflict" },
] as const;
