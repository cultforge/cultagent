import type { ReactNode } from "react";
import { Button } from "./Button";
import { isRunning } from "../lib/servers";

type Props = {
  state: string;
  busy?: boolean;
  size?: "md" | "xl";
  onAction: (action: "start" | "stop" | "restart") => void;
  extra?: ReactNode;
};

export function ServerActions({ state, busy, size = "md", onAction, extra }: Props) {
  const running = isRunning(state);
  return (
    <div className="flex flex-wrap items-center gap-2">
      {running ? (
        <>
          <Button variant="danger" size={size} disabled={busy} onClick={() => onAction("stop")}>
            Stop
          </Button>
          <Button size={size} disabled={busy} onClick={() => onAction("restart")}>
            Restart
          </Button>
        </>
      ) : (
        <Button variant="primary" size={size} disabled={busy} onClick={() => onAction("start")}>
          Start
        </Button>
      )}
      {extra}
    </div>
  );
}
