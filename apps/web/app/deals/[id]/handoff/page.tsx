import { notFound } from "next/navigation";

import { AppShell } from "../../../../components/app-shell";
import { StatTile } from "../../../../components/stat-tile";
import { ApiError, getAccountBrief, getHandoff } from "../../../../lib/api";

export const dynamic = "force-dynamic";

export default async function HandoffPage({
  params
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let brief;
  try {
    brief = await getHandoff(id);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }
  const account = await getAccountBrief(brief.account_id);

  return (
    <AppShell
      title="Closed-Won Handoff"
      subtitle="Activation-focused brief that preserves momentum after signature and turns telemetry into day-one tasks."
      agentContext={{ accountId: brief.account_id }}
    >
      <section className="grid stats-grid">
        <StatTile label="Deal" value={brief.deal_label} tone="cool" />
        <StatTile label="Blockers" value={brief.blockers.length} tone="warm" />
        <StatTile label="Telemetry Highlights" value={brief.telemetry_highlights.length} />
      </section>

      <section className="grid two-col">
        <article className="card stack-md">
          <div className="section-head">
            <h2>Activation Summary</h2>
            <span className="pill success">{brief.stage.replaceAll("_", " ")}</span>
          </div>
          <p>{brief.summary}</p>
          <p className="muted">
            {account.account.name}: {account.account.summary}
          </p>
          <div className="stack-sm">
            {brief.tasks.map((task) => (
              <div className="timeline-item" key={`${task.title}-${task.owner}`}>
                <strong>{task.title}</strong>
                <p>
                  {task.owner} | {task.window}
                </p>
              </div>
            ))}
          </div>
        </article>

        <article className="card stack-md">
          <div className="section-head">
            <h2>Likely Blockers</h2>
            <span className="pill neutral">{brief.blockers.length} risks</span>
          </div>
          <div className="stack-sm">
            {brief.blockers.map((blocker) => (
              <div className="rationale" key={`${blocker.title}-${blocker.severity}`}>
                <div className="rationale-head">
                  <strong>{blocker.title}</strong>
                  <span>{blocker.severity}</span>
                </div>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="grid two-col">
        <article className="card stack-md">
          <div className="section-head">
            <h2>Stakeholder Owners</h2>
            <span className="pill neutral">{brief.stakeholders.length} names</span>
          </div>
          <div className="stack-sm">
            {brief.stakeholders.map((stakeholder) => (
              <div className="person-row" key={`${stakeholder.name}-${stakeholder.role}`}>
                <div>
                  <strong>{stakeholder.name}</strong>
                  <p>{stakeholder.role}</p>
                </div>
                <div className="person-meta">
                  <span>{stakeholder.persona}</span>
                  <span>{stakeholder.status}</span>
                </div>
              </div>
            ))}
          </div>
        </article>

        <article className="card stack-md">
          <div className="section-head">
            <h2>Telemetry Highlights</h2>
            <span className="pill neutral">Expansion only</span>
          </div>
          <div className="stack-sm">
            {brief.telemetry_highlights.map((item) => (
              <div className="timeline-item" key={`${item.title}-${item.detail}`}>
                <strong>{item.title}</strong>
                <p>{item.detail}</p>
              </div>
            ))}
          </div>
        </article>
      </section>
    </AppShell>
  );
}
