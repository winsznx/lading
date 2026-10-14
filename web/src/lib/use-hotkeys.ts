import { useEffect, useLayoutEffect, useRef } from "react";

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  return target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT";
}

/** Single-key shortcuts. Ignored while typing, with modifiers held, or on key repeat. */
export function useHotkeys(onKey: (key: string) => void): void {
  const handler = useRef(onKey);
  useLayoutEffect(() => {
    handler.current = onKey;
  });

  useEffect(() => {
    function listener(event: KeyboardEvent): void {
      if (event.defaultPrevented || event.repeat || event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTyping(event.target)) return;
      handler.current(event.key);
    }
    window.addEventListener("keydown", listener);
    return () => {
      window.removeEventListener("keydown", listener);
    };
  }, []);
}
