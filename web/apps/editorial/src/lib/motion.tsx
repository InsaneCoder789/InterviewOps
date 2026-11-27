"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

type Motion = { on: boolean; ready: boolean; toggle: () => void };
const MotionContext = createContext<Motion>({ on: false, ready: false, toggle: () => {} });
export const useMotion = () => useContext(MotionContext);
export const MOTION_KEY = "io-motion";

/*
 * One switch for all movement. The initial value is written to <html data-motion> by the inline script in layout.tsx
 * before first paint (system reduced-motion or the reader's saved choice). With motion off there is no canvas, no cursor,
 * no pinning: the page is a plain illustrated article.
 */
export function MotionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState({ on: false, ready: false });

  useEffect(() => {
    setState({ on: document.documentElement.dataset.motion === "on", ready: true });
    const query = matchMedia("(prefers-reduced-motion: reduce)");
    const change = () => {
      if (!query.matches) return;
      document.documentElement.dataset.motion = "off";
      setState({ on: false, ready: true });
    };
    query.addEventListener("change", change);
    return () => query.removeEventListener("change", change);
  }, []);

  const toggle = () => {
    const on = !state.on;
    document.documentElement.dataset.motion = on ? "on" : "off";
    try { localStorage.setItem(MOTION_KEY, on ? "on" : "off"); } catch {}
    setState({ on, ready: true });
  };

  return <MotionContext.Provider value={{ ...state, toggle }}>{children}</MotionContext.Provider>;
}
