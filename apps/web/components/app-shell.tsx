import Link from "next/link";
import type { PropsWithChildren } from "react";

import { AgentSidebar } from "./agent-sidebar";

export function AppShell({
  title,
  subtitle,
  children,
  agentContext
}: PropsWithChildren<{
  title: string;
  subtitle: string;
  agentContext?: { accountId?: string; draftId?: string };
}>) {
  return (
    <div className="shell">
      <div className="ambient ambient-left" />
      <div className="ambient ambient-right" />
      <header className="hero">
        <div>
          <p className="eyebrow">Blostem B2B AI Marketing Engine</p>
          <h1>{title}</h1>
          <p className="subtitle">{subtitle}</p>
        </div>
        <nav className="topnav">
          <Link href="/">Queue</Link>
          {agentContext?.accountId ? <Link href={`/accounts/${agentContext.accountId}`}>Account Detail</Link> : null}
          {agentContext?.draftId ? <Link href={`/drafts/${agentContext.draftId}`}>Draft Review</Link> : null}
          {agentContext?.accountId ? <Link href={`/deals/${agentContext.accountId}/handoff`}>Handoff</Link> : null}
        </nav>
      </header>
      <div className="workspace">
        <main className="content">{children}</main>
      </div>
      <AgentSidebar accountId={agentContext?.accountId} draftId={agentContext?.draftId} />
    </div>
  );
}
