import Link from "next/link";

import { AppShell } from "../components/app-shell";
import { MarketDiscoveryPanel } from "../components/market-discovery-panel";
import { StatTile } from "../components/stat-tile";
import { getApiBaseUrl, getDiscoveryInbox, getDiscoveryJobs, getProductContexts, getQueue } from "../lib/api";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [queue, productContexts, discoveryJobs, scheduledCandidates] = await Promise.all([
    getQueue(),
    getProductContexts(),
    getDiscoveryJobs(),
    getDiscoveryInbox()
  ]);
  const top = queue.items[0];

  return (
    <AppShell
      title="Account Queue"
      subtitle="High-intent BFSI accounts ranked by fit, freshness, and approved next action."
      agentContext={{ accountId: top?.id }}
    >
      <MarketDiscoveryPanel
        discoveryJobs={discoveryJobs}
        productContexts={productContexts}
        scheduledCandidates={scheduledCandidates}
      />

      <section className="grid stats-grid">
        <StatTile label="Tracked Accounts" value={queue.items.length} tone="default" />
        <StatTile label="Top Intent" value={`${top?.intent_score ?? 0}%`} tone="warm" />
        <StatTile label="Primary Product" value={top?.product_context_key ?? "Pending"} tone="cool" />
      </section>

      <section className="grid queue-grid">
        {queue.items.length > 0 ? (
          queue.items.map((item) => (
            <article className="card queue-card" key={item.id}>
              <div className="section-head">
                <div>
                  <span className="eyebrow">{item.segment}</span>
                  <h2>{item.name}</h2>
                </div>
                <span className="pill neutral">{item.pipeline_stage}</span>
              </div>
              <div className="score-row">
                <span>Intent {item.intent_score}</span>
                <span>Fit {item.fit_score}</span>
                <span>Freshness {item.freshness_score}</span>
              </div>
              <p>{item.top_signal}</p>
              <p className="muted">{item.next_action}</p>
              <div className="actions">
                <Link href={`/accounts/${item.id}`}>Open account</Link>
                <Link href={`/deals/${item.id}/handoff`}>View handoff</Link>
              </div>
            </article>
          ))
        ) : (
          <article className="card stack-md empty-state-card">
            <div className="section-head">
              <div>
                <span className="eyebrow">Live Setup</span>
                <h2>No accounts yet</h2>
              </div>
              <span className="pill neutral">empty</span>
            </div>
            <p>The workspace is intentionally empty. The queue will populate only after you create product contexts, accounts, contacts, and signals.</p>
            <div className="stack-sm">
              <div className="timeline-item">
                <strong>1. Create a product context</strong>
                <p>POST to the backend docs with your ICP, personas, approved claims, and trigger patterns.</p>
              </div>
              <div className="timeline-item">
                <strong>2. Create an account and contacts</strong>
                <p>Use the Shadow CRM endpoints to add the enterprise and buying committee.</p>
              </div>
              <div className="timeline-item">
                <strong>3. Ingest real signals</strong>
                <p>Add public market signals and optional telemetry, then run opportunity refresh from the Copilot sidebar.</p>
              </div>
            </div>
            <div className="actions">
              <a href={`${getApiBaseUrl()}/docs`}>Open Backend Docs</a>
            </div>
          </article>
        )}
      </section>
    </AppShell>
  );
}
