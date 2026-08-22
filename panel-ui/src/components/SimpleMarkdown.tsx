/** Minimal safe markdown renderer (no raw HTML). */

import type { ReactNode } from "react";

function inline(text: string, keyPrefix: string): ReactNode[] {
  const parts: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) {
      parts.push(text.slice(last, m.index));
    }
    const token = m[0];
    const k = `${keyPrefix}-${i++}`;
    if (token.startsWith("**")) {
      parts.push(
        <strong key={k} className="font-semibold text-text">
          {token.slice(2, -2)}
        </strong>,
      );
    } else if (token.startsWith("*")) {
      parts.push(
        <em key={k} className="italic">
          {token.slice(1, -1)}
        </em>,
      );
    } else {
      parts.push(
        <code
          key={k}
          className="rounded bg-oled px-1 py-0.5 font-mono text-[12px] text-neon"
        >
          {token.slice(1, -1)}
        </code>,
      );
    }
    last = m.index + token.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export function SimpleMarkdown({ source }: { source: string }) {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let list: string[] = [];
  let para: string[] = [];
  let bi = 0;

  const flushList = () => {
    if (!list.length) return;
    blocks.push(
      <ul key={`ul-${bi++}`} className="my-2 list-disc space-y-1 pl-5 text-[13px] text-text-dim">
        {list.map((item, idx) => (
          <li key={idx}>{inline(item, `li-${bi}-${idx}`)}</li>
        ))}
      </ul>,
    );
    list = [];
  };

  const flushPara = () => {
    if (!para.length) return;
    const text = para.join(" ");
    blocks.push(
      <p key={`p-${bi++}`} className="my-2 text-[13px] leading-relaxed text-text-dim">
        {inline(text, `p-${bi}`)}
      </p>,
    );
    para = [];
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    const trimmed = line.trim();
    if (!trimmed) {
      flushList();
      flushPara();
      continue;
    }
    if (trimmed === "---" || trimmed === "***") {
      flushList();
      flushPara();
      blocks.push(<hr key={`hr-${bi++}`} className="my-4 border-border" />);
      continue;
    }
    if (trimmed.startsWith("### ")) {
      flushList();
      flushPara();
      blocks.push(
        <h4 key={`h3-${bi++}`} className="mb-1 mt-4 text-[13px] font-semibold text-text">
          {inline(trimmed.slice(4), `h3-${bi}`)}
        </h4>,
      );
      continue;
    }
    if (trimmed.startsWith("## ")) {
      flushList();
      flushPara();
      blocks.push(
        <h3 key={`h2-${bi++}`} className="mb-1 mt-4 text-[14px] font-semibold text-text">
          {inline(trimmed.slice(3), `h2-${bi}`)}
        </h3>,
      );
      continue;
    }
    if (trimmed.startsWith("# ")) {
      flushList();
      flushPara();
      blocks.push(
        <h2 key={`h1-${bi++}`} className="mb-2 mt-3 text-[15px] font-semibold text-text">
          {inline(trimmed.slice(2), `h1-${bi}`)}
        </h2>,
      );
      continue;
    }
    if (trimmed.startsWith("> ")) {
      flushList();
      flushPara();
      blocks.push(
        <blockquote
          key={`bq-${bi++}`}
          className="my-2 border-l-2 border-neon/40 pl-3 text-[13px] text-muted"
        >
          {inline(trimmed.slice(2), `bq-${bi}`)}
        </blockquote>,
      );
      continue;
    }
    const bullet = trimmed.match(/^[-*] (.+)$/);
    if (bullet) {
      flushPara();
      list.push(bullet[1]);
      continue;
    }
    flushList();
    para.push(trimmed);
  }
  flushList();
  flushPara();

  return <div className="markdown-body">{blocks}</div>;
}
