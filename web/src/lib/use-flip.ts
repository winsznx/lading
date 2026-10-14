import { useCallback, useLayoutEffect, useRef, type RefObject } from "react";

const FLIP_MS = 160;
const EASE_OUT = "cubic-bezier(0.2, 0, 0, 1)";

function reducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export interface Flip {
  containerRef: RefObject<HTMLDivElement>;
  /** Record where every `[data-flip-key]` element sits now, just before the board re-renders. */
  capture: () => void;
}

/**
 * FLIP for plan cards: after a new plan commits (`version` changes), each card that existed before is
 * moved back to its old spot with a transform and animated to its new cell.
 */
export function useFlip(version: number): Flip {
  const containerRef = useRef<HTMLDivElement>(null);
  const before = useRef<Map<string, DOMRect> | null>(null);

  const capture = useCallback(() => {
    const root = containerRef.current;
    if (!root || reducedMotion()) {
      before.current = null;
      return;
    }
    const rects = new Map<string, DOMRect>();
    root.querySelectorAll<HTMLElement>("[data-flip-key]").forEach((element) => {
      const key = element.dataset.flipKey;
      if (key) rects.set(key, element.getBoundingClientRect());
    });
    before.current = rects;
  }, []);

  useLayoutEffect(() => {
    const previous = before.current;
    before.current = null;
    const root = containerRef.current;
    if (!previous || !root) return;
    root.querySelectorAll<HTMLElement>("[data-flip-key]").forEach((element) => {
      const key = element.dataset.flipKey;
      const from = key ? previous.get(key) : undefined;
      if (!from) return;
      const to = element.getBoundingClientRect();
      const dx = from.left - to.left;
      const dy = from.top - to.top;
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return;
      element.style.zIndex = "2";
      const animation = element.animate(
        [{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "translate(0, 0)" }],
        { duration: FLIP_MS, easing: EASE_OUT },
      );
      animation.onfinish = () => {
        element.style.zIndex = "";
      };
    });
  }, [version]);

  return { containerRef, capture };
}
