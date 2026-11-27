/* One passive listener and one animation frame, shared by every chapter. */
const watchers = new Set<() => void>();
let frame = 0;

const run = () => {
  frame = 0;
  watchers.forEach((watcher) => watcher());
};
const schedule = () => {
  if (!frame) frame = requestAnimationFrame(run);
};

export function watchScroll(watcher: () => void) {
  if (!watchers.size) {
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
  }
  watchers.add(watcher);
  schedule();
  return () => {
    watchers.delete(watcher);
    if (watchers.size) return;
    window.removeEventListener("scroll", schedule);
    window.removeEventListener("resize", schedule);
    cancelAnimationFrame(frame);
    frame = 0;
  };
}
