import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { isAbortError } from "../api/client";

export type Resource<T> = { status: "loading" } | { status: "ready"; data: T } | { status: "error"; error: unknown };

interface Keyed<T> {
  key: string;
  resource: Resource<T>;
}

const LOADING = { status: "loading" } as const;

/**
 * Fetch once per `key`, abort on change or unmount, and expose `reload` for error states.
 * Results are tagged with their key so a stale answer never shows under a new key.
 */
export function useResource<T>(key: string, load: (signal: AbortSignal) => Promise<T>): [Resource<T>, () => void] {
  const loader = useRef(load);
  useLayoutEffect(() => {
    loader.current = load;
  });
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<Keyed<T> | null>(null);
  const tag = `${key}#${attempt}`;

  useEffect(() => {
    const controller = new AbortController();
    loader.current(controller.signal).then(
      (data) => {
        setState({ key: tag, resource: { status: "ready", data } });
      },
      (error: unknown) => {
        if (!isAbortError(error)) setState({ key: tag, resource: { status: "error", error } });
      },
    );
    return () => {
      controller.abort();
    };
  }, [tag]);

  const reload = useCallback(() => {
    setAttempt((n) => n + 1);
  }, []);

  return [state?.key === tag ? state.resource : LOADING, reload];
}
