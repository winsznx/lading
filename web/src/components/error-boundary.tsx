import { Component, type ErrorInfo, type ReactNode } from "react";

import { AlertIcon } from "./icons";
import { Button } from "./primitives";

interface Props {
  /** What failed, in the reader's words: "the held-out section". */
  what: string;
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Keeps one broken panel (say, a results file with an unexpected shape) from blanking the whole console. */
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(`Lading console: ${this.props.what} failed to render`, error, info.componentStack);
  }

  override render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div role="alert" className="flex items-start gap-3 rounded border border-bad bg-bad-wash p-3 text-ink">
        <AlertIcon className="mt-0.5 shrink-0 text-bad" />
        <div className="min-w-0 flex-1">
          <p className="text-13 font-semibold">Couldn&apos;t show {this.props.what}</p>
          <p className="mt-0.5 text-13 text-ink-2">
            The data arrived in a shape this console doesn&apos;t read. {error.message}
          </p>
        </div>
        <Button
          size="sm"
          onClick={() => {
            this.setState({ error: null });
          }}
        >
          Try again
        </Button>
      </div>
    );
  }
}
