"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { startTransition, useState } from "react";

import {
  ApiError,
  addDiscoveryCandidate,
  createDiscoveryJob,
  createProductContext,
  runDiscoveryJob,
  runDueAutomation,
  searchDiscovery
} from "../lib/api";
import type {
  DiscoveryCandidate,
  DiscoveryCandidateRecord,
  DiscoveryJob,
  DiscoverySearchResponse,
  ProductContext
} from "../lib/types";

// ── Shared helper: build a discovery prompt from a product context's metadata ──
function buildPromptForContext(
  icp: string[],
  triggers: string[],
  name: string
): string {
  const icpPhrase    = icp.length     > 0 ? icp.join(", ")                          : "BFSI organizations";
  const triggerPhrase = triggers.length > 0 ? `showing signs of ${triggers.slice(0, 4).join(", ")}` : "with recent market signals";
  return `Find Indian ${icpPhrase} ${triggerPhrase} that suggest active need for ${name}.`;
}

export function MarketDiscoveryPanel({
  discoveryJobs,
  productContexts,
  scheduledCandidates
}: {
  discoveryJobs: DiscoveryJob[];
  productContexts: ProductContext[];
  scheduledCandidates: DiscoveryCandidateRecord[];
}) {
  const router = useRouter();

  // ── Discovery search state ──────────────────────────────────────────────────
  const [selectedContext, setSelectedContext] = useState(productContexts[0]?.key ?? "");
  const [prompt, setPrompt] = useState(() => {
    const first = productContexts[0];
    return first
      ? buildPromptForContext(first.icp_segments, first.trigger_patterns, first.name)
      : "";
  });
  const [cadenceMinutes, setCadenceMinutes] = useState(360);
  const [results, setResults] = useState<DiscoverySearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [isScheduling, setIsScheduling] = useState(false);
  const [isRunningAutomation, setIsRunningAutomation] = useState(false);
  const [runningJobId, setRunningJobId] = useState<string | null>(null);
  const [addingCandidateId, setAddingCandidateId] = useState<string | null>(null);
  const [addedAccounts, setAddedAccounts] = useState<Record<string, string>>({});

  // ── Create product context form state ──────────────────────────────────────
  const [showContextForm, setShowContextForm] = useState(productContexts.length === 0);
  const [ctxKey, setCtxKey] = useState("");
  const [ctxName, setCtxName] = useState("");
  const [ctxOverview, setCtxOverview] = useState("");
  const [ctxIcp, setCtxIcp] = useState("");
  const [ctxTriggers, setCtxTriggers] = useState("");
  const [ctxDisqualifiers, setCtxDisqualifiers] = useState("");
  const [isCreatingCtx, setIsCreatingCtx] = useState(false);
  const [ctxError, setCtxError] = useState<string | null>(null);

  // ── Helpers ─────────────────────────────────────────────────────────────────
  function deriveKey(name: string) {
    return name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
  }

  function handleCtxNameChange(value: string) {
    setCtxName(value);
    // Auto-fill key only if the user hasn't manually edited it yet
    if (!ctxKey || ctxKey === deriveKey(ctxName)) {
      setCtxKey(deriveKey(value));
    }
  }

  // ── Actions ──────────────────────────────────────────────────────────────────
  function createCtx() {
    if (!ctxKey.trim() || !ctxName.trim() || !ctxOverview.trim()) return;
    setCtxError(null);
    setIsCreatingCtx(true);
    const splitCommaNewline = (raw: string) =>
      raw.split(/[,\n]/).map((s) => s.trim()).filter(Boolean);

    // Capture values before clearing the form
    const newKey      = ctxKey.trim();
    const newName     = ctxName.trim();
    const newIcp      = splitCommaNewline(ctxIcp);
    const newTriggers = splitCommaNewline(ctxTriggers);

    // Build an auto-search prompt reusing the shared helper
    function buildAutoPrompt(): string {
      return buildPromptForContext(newIcp, newTriggers, newName);
    }

    startTransition(() => {
      void createProductContext({
        key: newKey,
        name: newName,
        overview: ctxOverview.trim(),
        icp_segments: newIcp,
        trigger_patterns: newTriggers,
        disqualifiers: splitCommaNewline(ctxDisqualifiers)
      })
        .then(() => {
          const autoPrompt = buildAutoPrompt();
          setCtxKey(""); setCtxName(""); setCtxOverview("");
          setCtxIcp(""); setCtxTriggers(""); setCtxDisqualifiers("");
          setShowContextForm(false);
          setSelectedContext(newKey);
          setPrompt(autoPrompt);
          // Auto-launch discovery search with the new context
          setError(null);
          setIsSearching(true);
          setResults(null);
          void searchDiscovery({ prompt: autoPrompt, product_context_key: newKey, limit: 8 })
            .then((response) => { setResults(response); })
            .catch((nextError: Error) => {
              setError(nextError instanceof ApiError ? nextError.message : "Auto-discovery failed.");
            })
            .finally(() => { setIsSearching(false); });
          router.refresh();
        })
        .catch((nextError: Error) => {
          setCtxError(
            nextError instanceof ApiError
              ? nextError.message
              : "Could not create product context."
          );
        })
        .finally(() => { setIsCreatingCtx(false); });
    });
  }

  function runSearch() {
    const trimmedPrompt = prompt.trim();
    if (!trimmedPrompt) return;
    setError(null);
    setIsSearching(true);
    startTransition(() => {
      void searchDiscovery({
        prompt: trimmedPrompt,
        product_context_key: selectedContext || undefined,
        limit: 8
      })
        .then((response) => { setResults(response); })
        .catch((nextError: Error) => {
          setError(nextError instanceof ApiError ? nextError.message : "Discovery search failed.");
        })
        .finally(() => { setIsSearching(false); });
    });
  }

  function scheduleSearch() {
    const trimmedPrompt = prompt.trim();
    if (!trimmedPrompt || !selectedContext) return;
    setError(null);
    setIsScheduling(true);
    startTransition(() => {
      void createDiscoveryJob({
        product_context_key: selectedContext,
        prompt: trimmedPrompt,
        cadence_minutes: cadenceMinutes,
        limit: 8,
        auto_import_threshold: 0
      })
        .then(() => { router.refresh(); })
        .catch((nextError: Error) => {
          setError(nextError instanceof ApiError ? nextError.message : "Could not schedule discovery.");
        })
        .finally(() => { setIsScheduling(false); });
    });
  }

  function runJob(jobId: string) {
    setRunningJobId(jobId);
    setError(null);
    startTransition(() => {
      void runDiscoveryJob(jobId)
        .then(() => { router.refresh(); })
        .catch((nextError: Error) => {
          setError(nextError instanceof ApiError ? nextError.message : "Scheduled job run failed.");
        })
        .finally(() => { setRunningJobId(null); });
    });
  }

  function runAllDue() {
    setIsRunningAutomation(true);
    setError(null);
    startTransition(() => {
      void runDueAutomation()
        .then(() => { router.refresh(); })
        .catch((nextError: Error) => {
          setError(nextError instanceof ApiError ? nextError.message : "Automation run failed.");
        })
        .finally(() => { setIsRunningAutomation(false); });
    });
  }

  function addCandidate(candidate: DiscoveryCandidate, candidateRecordId?: string) {
    setAddingCandidateId(candidate.id);
    setError(null);
    startTransition(() => {
      void addDiscoveryCandidate({
        candidate,
        candidate_record_id: candidateRecordId,
        refresh_workflow: true
      })
        .then((response) => {
          setAddedAccounts((current) => ({
            ...current,
            [candidate.id]: response.account.id,
            ...(candidateRecordId ? { [candidateRecordId]: response.account.id } : {})
          }));
          router.refresh();
        })
        .catch((nextError: Error) => {
          setError(nextError instanceof ApiError ? nextError.message : "Import failed.");
        })
        .finally(() => { setAddingCandidateId(null); });
    });
  }

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <section className="card discovery-panel stack-md">
      <div className="section-head">
        <div>
          <span className="eyebrow">External Discovery</span>
          <h2>Find net-new orgs</h2>
        </div>
        <span className="pill neutral">{productContexts.length} product contexts</span>
      </div>

      <p className="muted">
        Prompt the discovery engine with a product context. It will search public signals, rank
        likely interested organizations, and let you add the ones you want into the interested queue.
      </p>

      {/* ── Create product context accordion ── */}
      <div className="ctx-form-wrapper">
        <button
          className="ghost-button ctx-toggle"
          onClick={() => setShowContextForm((v) => !v)}
          type="button"
        >
          {showContextForm ? "▲ Hide" : "＋ New product context"}
        </button>

        {showContextForm && (
          <div className="ctx-form stack-sm">
            <p className="muted">
              Define your product so the discovery engine knows what organizations to target.
              ICP segments and trigger patterns can be comma-separated.
            </p>

            <div className="ctx-form-grid">
              <label className="field-label">
                Product name <span className="required">*</span>
                <input
                  className="agent-input"
                  onChange={(e) => handleCtxNameChange(e.target.value)}
                  placeholder="Log Investigation Framework"
                  type="text"
                  value={ctxName}
                />
              </label>

              <label className="field-label">
                Key (slug) <span className="required">*</span>
                <input
                  className="agent-input"
                  onChange={(e) => setCtxKey(e.target.value)}
                  placeholder="log_investigation_framework"
                  type="text"
                  value={ctxKey}
                />
              </label>
            </div>

            <label className="field-label">
              Overview <span className="required">*</span>
              <textarea
                className="agent-textarea"
                onChange={(e) => setCtxOverview(e.target.value)}
                placeholder="Describe what the product does and who it helps…"
                rows={3}
                value={ctxOverview}
              />
            </label>

            <label className="field-label">
              ICP segments <span className="hint">(comma-separated)</span>
              <input
                className="agent-input"
                onChange={(e) => setCtxIcp(e.target.value)}
                placeholder="Bank, Fintech, NBFC, Insurance"
                type="text"
                value={ctxIcp}
              />
            </label>

            <label className="field-label">
              Trigger patterns <span className="hint">(comma-separated)</span>
              <input
                className="agent-input"
                onChange={(e) => setCtxTriggers(e.target.value)}
                placeholder="cyber attack, RBI audit, fraud investigation, SIEM, data breach"
                type="text"
                value={ctxTriggers}
              />
            </label>

            <label className="field-label">
              Disqualifiers <span className="hint">(optional, comma-separated)</span>
              <input
                className="agent-input"
                onChange={(e) => setCtxDisqualifiers(e.target.value)}
                placeholder="non-financial, retail only"
                type="text"
                value={ctxDisqualifiers}
              />
            </label>

            {ctxError ? <p className="error-text">{ctxError}</p> : null}

            <p className="muted ctx-auto-hint">
              After creating, the engine will automatically search for the most interested organizations matching your product. Results will appear below.
            </p>

            <div className="actions">
              <button
                className="primary-button"
                disabled={isCreatingCtx || !ctxKey.trim() || !ctxName.trim() || !ctxOverview.trim()}
                onClick={createCtx}
                type="button"
              >
                {isCreatingCtx ? "Creating & searching…" : "Create & find interested parties"}
              </button>
              {productContexts.length > 0 && (
                <button
                  className="ghost-button"
                  onClick={() => setShowContextForm(false)}
                  type="button"
                >
                  Cancel
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ── Discovery search form ── */}
      {productContexts.length === 0 ? (
        <div className="empty-hint">
          <p>Create at least one product context above before running external discovery.</p>
        </div>
      ) : (
        <>
          <div className="discovery-form">
            <label className="field-label">
              Product context
              <select
                className="agent-select"
                onChange={(event) => {
                  const key = event.target.value;
                  setSelectedContext(key);
                  const ctx = productContexts.find((c) => c.key === key);
                  if (ctx) {
                    setPrompt(buildPromptForContext(ctx.icp_segments, ctx.trigger_patterns, ctx.name));
                    setResults(null); // clear stale results from previous context
                  }
                }}
                value={selectedContext}
              >
                {productContexts.map((context) => (
                  <option key={context.key} value={context.key}>
                    {context.name}
                  </option>
                ))}
              </select>
            </label>

            <label className="field-label">
              Discovery prompt
              <textarea
                className="agent-textarea discovery-textarea"
                onChange={(event) => setPrompt(event.target.value)}
                placeholder="Find banks, fintechs, or agencies showing active need for this product."
                rows={4}
                value={prompt}
              />
            </label>
          </div>

          <div className="actions">
            <button
              className="primary-button"
              disabled={isSearching || !prompt.trim()}
              onClick={runSearch}
              type="button"
            >
              {isSearching ? "Searching..." : "Search the public web"}
            </button>
            <button
              className="ghost-button"
              disabled={isScheduling || !prompt.trim() || !selectedContext}
              onClick={scheduleSearch}
              type="button"
            >
              {isScheduling ? "Scheduling..." : "Schedule recurring search"}
            </button>
            <button
              className="ghost-button"
              disabled={isRunningAutomation}
              onClick={runAllDue}
              type="button"
            >
              {isRunningAutomation ? "Running..." : "Run due automation"}
            </button>
          </div>

          <label className="field-label compact-field">
            Cadence
            <select
              className="agent-select"
              onChange={(event) => setCadenceMinutes(Number(event.target.value))}
              value={cadenceMinutes}
            >
              <option value={60}>Hourly</option>
              <option value={360}>Every 6 hours</option>
              <option value={1440}>Daily</option>
            </select>
          </label>
        </>
      )}

      {error ? <p className="error-text">{error}</p> : null}

      {/* ── Discovery results ── */}
      {results ? (
        <div className="stack-md">
          <div className="section-head">
            <div>
              <span className="eyebrow">Discovery Results</span>
              <h3>{results.candidates.length} ranked candidates</h3>
            </div>
            <span className="pill neutral">{results.product_context_name}</span>
          </div>

          {results.queries.length > 0 ? (
            <div className="quick-commands">
              {results.queries.map((query) => (
                <span className="context-chip" key={query}>
                  {query}
                </span>
              ))}
            </div>
          ) : null}

          {results.notes.length > 0 ? (
            <div className="stack-sm">
              {results.notes.map((note) => (
                <div className="timeline-item" key={note}>
                  <p>{note}</p>
                </div>
              ))}
            </div>
          ) : null}

          <div className="grid queue-grid">
            {results.candidates.map((candidate) => {
              const addedAccountId = addedAccounts[candidate.id];
              const isAdding = addingCandidateId === candidate.id;
              return (
                <article className="card queue-card discovery-card" key={candidate.id}>
                  <div className="section-head">
                    <div>
                      <span className="eyebrow">{candidate.segment}</span>
                      <h3>{candidate.name}</h3>
                    </div>
                    <span className="pill neutral">{candidate.product_context_key}</span>
                  </div>

                  <div className="score-row">
                    <span>Interest {candidate.interest_score}</span>
                    <span>Fit {candidate.fit_score}</span>
                    <span>Freshness {candidate.freshness_score}</span>
                  </div>

                  <p>{candidate.top_signal}</p>
                  <p className="muted">{candidate.reason}</p>

                  {candidate.reasons.length > 0 ? (
                    <ul className="message-list">
                      {candidate.reasons.slice(0, 4).map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  ) : null}

                  {candidate.citations.length > 0 ? (
                    <div className="message-citations">
                      {candidate.citations.slice(0, 3).map((citation) => (
                        <a
                          className="mini-citation"
                          href={citation.source_url}
                          key={`${candidate.id}-${citation.source_url}`}
                          rel="noreferrer"
                          target="_blank"
                        >
                          {citation.label}
                        </a>
                      ))}
                    </div>
                  ) : null}

                  <div className="actions">
                    <button
                      className="primary-button"
                      disabled={Boolean(addedAccountId) || isAdding}
                      onClick={() => addCandidate(candidate)}
                      type="button"
                    >
                      {addedAccountId ? "Added to queue" : isAdding ? "Adding..." : "Add to interested queue"}
                    </button>
                    {addedAccountId ? <Link href={`/accounts/${addedAccountId}`}>Open account</Link> : null}
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      ) : null}

      {/* ── Scheduled jobs & candidate inbox ── */}
      {discoveryJobs.length > 0 || scheduledCandidates.length > 0 ? (
        <div className="grid two-col">
          <article className="card stack-md subtle-card">
            <div className="section-head">
              <div>
                <span className="eyebrow">Scheduled Listening</span>
                <h3>{discoveryJobs.length} active jobs</h3>
              </div>
            </div>
            <div className="stack-sm">
              {discoveryJobs.slice(0, 4).map((job) => (
                <div className="timeline-item" key={job.id}>
                  <strong>{job.product_context_key}</strong>
                  <p>{job.prompt}</p>
                  <p className="muted">
                    Every {job.cadence_minutes} min · last results {job.last_result_count} · next{" "}
                    {job.next_run_at ? new Date(job.next_run_at).toLocaleString() : "now"}
                  </p>
                  <button
                    className="ghost-button"
                    disabled={runningJobId === job.id}
                    onClick={() => runJob(job.id)}
                    type="button"
                  >
                    {runningJobId === job.id ? "Running..." : "Run now"}
                  </button>
                </div>
              ))}
            </div>
          </article>

          <article className="card stack-md subtle-card">
            <div className="section-head">
              <div>
                <span className="eyebrow">Candidate Inbox</span>
                <h3>{scheduledCandidates.length} to review</h3>
              </div>
            </div>
            <div className="stack-sm">
              {scheduledCandidates.slice(0, 5).map((record) => {
                const addedAccountId = addedAccounts[record.id] || addedAccounts[record.candidate.id];
                const isAdding = addingCandidateId === record.candidate.id;
                return (
                  <div className="timeline-item" key={record.id}>
                    <strong>{record.candidate.name}</strong>
                    <p>{record.candidate.top_signal}</p>
                    <p className="muted">
                      Interest {record.candidate.interest_score} · confidence {record.confidence_score} · {record.source_count} sources
                    </p>
                    <div className="actions">
                      <button
                        className="primary-button"
                        disabled={Boolean(addedAccountId) || isAdding}
                        onClick={() => addCandidate(record.candidate, record.id)}
                        type="button"
                      >
                        {addedAccountId ? "Added" : isAdding ? "Adding..." : "Add to queue"}
                      </button>
                      {addedAccountId ? <Link href={`/accounts/${addedAccountId}`}>Open account</Link> : null}
                    </div>
                  </div>
                );
              })}
            </div>
          </article>
        </div>
      ) : null}
    </section>
  );
}
