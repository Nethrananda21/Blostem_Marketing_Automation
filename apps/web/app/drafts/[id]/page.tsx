import { notFound } from "next/navigation";

import { AppShell } from "../../../components/app-shell";
import { CitationList } from "../../../components/citation-list";
import { CompliancePanel } from "../../../components/compliance-panel";
import { DraftActions } from "../../../components/draft-actions";
import { RationaleList } from "../../../components/rationale-list";
import { ApiError, getAccountBrief, getDraft } from "../../../lib/api";

export const dynamic = "force-dynamic";

export default async function DraftPage({
  params
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let draft;
  try {
    draft = await getDraft(id);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }
  const brief = await getAccountBrief(draft.account_id);

  return (
    <AppShell
      title="Draft Review"
      subtitle="Rep-facing review surface with source-linked evidence, rationale, and compliance receipt."
      agentContext={{ accountId: draft.account_id, draftId: draft.id }}
    >
      {/* ── Draft body + actions ── */}
      <section className="card stack-md" style={{ marginBottom: "18px" }}>
        <div className="section-head">
          <div>
            <span className="eyebrow">{brief.account.name}</span>
            <h2>{draft.subject}</h2>
          </div>
          <span className={draft.status.includes("approval") ? "pill success" : draft.status === "approved" ? "pill success" : "pill danger"}>
            {draft.status.replaceAll("_", " ")}
          </span>
        </div>

        <pre className="draft-body">{draft.edited_body ?? draft.body}</pre>

        {/* Approve / Reject / Edit — only shown when not already terminal */}
        <DraftActions
          draftId={draft.id}
          initialStatus={draft.status}
          initialBody={draft.edited_body ?? draft.body}
          persona={draft.persona}
        />
      </section>

      {/* ── Rationale + compliance ── */}
      <section className="grid two-col">
        <article className="card stack-md">
          <div className="section-head">
            <h3>Structured Rationale</h3>
            <span className="pill neutral">{draft.persona}</span>
          </div>
          <RationaleList steps={draft.rationale} />
        </article>
        <CompliancePanel receipt={draft.compliance_receipt} />
      </section>

      {/* ── Citations + model route ── */}
      <section className="grid two-col">
        <article className="card stack-md">
          <div className="section-head">
            <h3>Citations</h3>
            <span className="pill neutral">{draft.citations.length} linked</span>
          </div>
          <CitationList citations={draft.citations} />
        </article>

        <article className="card stack-md">
          <div className="section-head">
            <h3>Model Route</h3>
            <span className="pill neutral">{draft.model_route.provider}</span>
          </div>
          <p>{draft.model_route.reason}</p>
          <dl className="route-grid">
            <div>
              <dt>Workflow</dt>
              <dd>{draft.model_route.workflow}</dd>
            </div>
            <div>
              <dt>Model</dt>
              <dd>{draft.model_route.model}</dd>
            </div>
            <div>
              <dt>Thinking</dt>
              <dd>{draft.model_route.thinking ? "Enabled" : "Disabled"}</dd>
            </div>
          </dl>
        </article>
      </section>
    </AppShell>
  );
}
