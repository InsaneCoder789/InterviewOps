"use client";

import dynamic from "next/dynamic";
import { MotionProvider, useMotion } from "@/lib/motion";
import { Boot } from "./boot/Boot";
import { Masthead } from "./chrome/Chrome";
import { CursorField } from "./cursor/CursorField";
import { Access } from "./sections/Access";
import { Anatomy, Enter, Hero, Locks } from "./sections/chapters";
import { Constraints } from "./sections/Constraints";
import { Deadlock } from "./sections/Deadlock";
import { Limits } from "./sections/Limits";
import { Reminders } from "./sections/Reminders";
import { Why } from "./sections/Why";

// three.js is a separate download that starts after the words are on screen, and not at all with motion off
const World = dynamic(() => import("./world/World"), { ssr: false });

function Layers() {
  const { on } = useMotion();
  return (
    <>
      {on && <World />}
      {on && <CursorField />}
      <Boot />
    </>
  );
}

export function Experience() {
  return (
    <MotionProvider>
      <a className="skip" href="#main">Skip to the story</a>
      <Layers />
      <div data-page>
        <Masthead />
        <main id="main">
          <Hero />
          <Why />
          <Anatomy />
          <Locks />
          <Constraints />
          <Deadlock />
          <Reminders />
          <Access />
          <Limits />
          <Enter />
        </main>
        <footer><span>InterviewOps. Mock interviews, booked without collisions.</span><span>MIT licence</span></footer>
      </div>
    </MotionProvider>
  );
}
