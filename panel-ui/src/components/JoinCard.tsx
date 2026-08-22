import { Link } from "react-router-dom";
import type { JoinInfo } from "../lib/api";
import { Button } from "./Button";

type Props = {
  join?: JoinInfo | null;
  port: number;
  onCopied?: (ok: boolean) => void;
};

export function JoinCard({ join, port, onCopied }: Props) {
  const primary = join?.primary || `localhost:${port}`;
  const localhost = join?.localhost || `localhost:${port}`;

  async function copy() {
    try {
      await navigator.clipboard.writeText(primary);
      onCopied?.(true);
    } catch {
      onCopied?.(false);
    }
  }

  return (
    <div className="cf-panel flex flex-col p-5">
      <h2 className="m-0 text-[11px] font-medium uppercase tracking-wider text-muted">
        Join address
      </h2>
      <p className="mt-2 break-all font-mono text-[15px] font-medium text-neon">{primary}</p>
      <Button variant="primary" className="mt-3 w-full" onClick={copy}>
        Copy address
      </Button>
      <dl className="mt-4 space-y-2.5 border-t border-border pt-4 text-[13px]">
        <div className="flex justify-between gap-3">
          <dt className="shrink-0 text-muted">This PC</dt>
          <dd className="m-0 break-all text-right font-mono text-text-dim">{localhost}</dd>
        </div>
        {join?.lan && (
          <div className="flex justify-between gap-3">
            <dt className="shrink-0 text-muted">LAN</dt>
            <dd className="m-0 break-all text-right font-mono text-text-dim">{join.lan}</dd>
          </div>
        )}
        <div className="flex justify-between gap-3">
          <dt className="shrink-0 text-muted">Public</dt>
          <dd className="m-0 break-all text-right font-mono text-text-dim">
            {join?.public ? (
              join.public
            ) : (
              <Link to="/network" className="text-text-dim hover:text-neon">
                Configure playit
              </Link>
            )}
          </dd>
        </div>
      </dl>
    </div>
  );
}
