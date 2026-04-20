import Link from "next/link";
import { notFound } from "next/navigation";

import { AppShell } from "../../../components/app-shell";
import { CitationList } from "../../../components/citation-list";
import { RationaleList } from "../../../components/rationale-list";
import { StatTile } from "../../../components/stat-tile";
import { ApiError, getAccountBrief } from "../../../lib/api";

export const dynamic = "force-dynamic";

export default async function AccountPage({
  params
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let brief;
  try {
    brief = await getAccountBrief(id);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }
  const opportunity = brief.opportunities[0];
  const draft = brief.drafts[0];

  return (
    <AppShell
      title={brief.account.name}
      subtitle="Glass-box account detail with stakeholder map, evidence, workflow rationale, and next rep action."
      agentContext={{ accountId: brief.account.id }}
    >
      <section className="grid stats-grid">
        <StatTile label="Intent" value={`${brief.account.intent_score}%`} tone="warm" />
        <StatTile label="Fit" value={`${brief.account.fit_score}%`} tone="cool" />
        <StatTile label="Stage" value={brief.account.pipeline_stage} />
      </section>

      <section className="grid two-col">
        <article className="card stack-md">
          <div className="section-head">
            <h2>Opportunity Brief</h2>
            <span className="pill success">{opportunity?.product_context_key ?? "Pending"}</span>
          </div>
          <p>{brief.account.summary}</p>
          <p className="muted">{brief.account.next_action}</p>
          {opportunity ? <RationaleList steps={opportunity.rationale} /> : null}
          <div className="actions">
            {draft ? <Link href={`/drafts/${draft.id}`}>Open draft review</Link> : null}
            <Link href={`/deals/${brief.account.id}/handoff`}>Open closed-won handoff</Link>
          </div>
        </article>

        <article className="card stack-md">
          <div className="section-head">
            <h2>Buying Committee</h2>
            <span className="pill neutral">{brief.contacts.length} mapped</span>
          </div>
          <div className="stack-sm">
            {brief.contacts.map((contact) => (
              <div className="person-row" key={contact.email}>
                <div>
                  <strong>{contact.name}</strong>
                  <p>{contact.role}</p>
                </div>
                <div className="person-meta">
                  <span>{contact.influence_level}</span>
                  <span>{contact.status}</span>
                </div>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="grid two-col">
        <article className="card stack-md">
          <div className="section-head">
            <h2>Nurture Automation</h2>
            <span className="pill neutral">{brief.nurture_sequences.length} sequences</span>
          </div>
          <div className="stack-sm">
            {brief.nurture_sequences.length > 0 ? (
              brief.nurture_sequences.map((sequence) => (
                <div className="timeline-item" key={sequence.id}>
                  <strong>{sequence.kind.replaceAll("_", " ")}</strong>
                  <p>
                    {sequence.stage} · round {sequence.current_round}/{sequence.max_rounds} · {sequence.status}
                  </p>
                  <p className="muted">
                    Next touch {sequence.next_touch_at ? new Date(sequence.next_touch_at).toLocaleString() : "not scheduled"}
                  </p>
                </div>
              ))
            ) : (
              <p className="muted">No active nurture sequence yet. Run opportunity refresh or create a closed-won handoff.</p>
            )}
          </div>
        </article>

        <article className="card stack-md">
          <div className="section-head">
            <h2>Pending Touches</h2>
            <span className="pill neutral">{brief.nurture_touches.length} touches</span>
          </div>
          <div className="stack-sm">
            {brief.nurture_touches.slice(0, 6).map((touch) => (
              <div className="timeline-item" key={touch.id}>
                <strong>
                  {touch.persona} · {touch.touch_kind.replaceAll("_", " ")}
                </strong>
                <p>{touch.summary}</p>
                <p className="muted">Status {touch.status}</p>
                {touch.draft_id ? <Link href={`/drafts/${touch.draft_id}`}>Review draft</Link> : null}
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="grid two-col">
        <article className="card stack-md">
          <div className="section-head">
            <h2>Evidence</h2>
            <span className="pill neutral">{brief.signals.length} signals</span>
          </div>
          <CitationList citations={opportunity?.evidence ?? []} />
        </article>

        <article className="card stack-md">
          <div className="section-head">
            <h2>Recent Activity</h2>
            <span className="pill neutral">Shadow CRM</span>
          </div>
          <div className="stack-sm">
            {brief.activity.map((item) => (
              <div className="timeline-item" key={item.id}>
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
