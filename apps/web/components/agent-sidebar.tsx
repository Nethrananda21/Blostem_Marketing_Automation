"use client";

import { useEffect, useRef, useState } from "react";

import { createAgentJob, getAgentJob, getApiBaseUrl, getSystemStatus, searchDiscovery } from "../lib/api";
import type { AgentResult, AgentRunRequest, DiscoverySearchResponse, SystemStatus } from "../lib/types";

type AgentSidebarProps = {
  accountId?: string;
  draftId?: string;
};

type ChatMessage = {
  id: string;
  role: "assistant" | "user" | "system";
  content: string;
  meta?: string;
  actions?: string[];
  citations?: AgentResult["citations"];
  tone?: "default" | "error";
};

const quickCommands = [
  { label: "/refresh", prompt: "/refresh Refresh this opportunity.", requires: "account" as const },
  { label: "/review", prompt: "/review Review the current draft.", requires: "draft" as const },
  { label: "/handoff", prompt: "/handoff Generate a closed-won handoff.", requires: "account" as const },
  { label: "/summarize", prompt: "/summarize Summarize the current account.", requires: "account" as const }
];

const starterPrompts = [
  "Why is this account high intent right now?",
  "What should I ask the CTO on the first call?",
  "/refresh Refresh and regenerate the latest opportunity.",
  "/review Review the current draft for citation or compliance risks."
];

function humanizeLabel(value: string): string {
  return value.replaceAll("_", " ");
}

function compactIdentifier(value: string): string {
  if (value.length <= 18) {
    return value;
  }
  return `${value.slice(0, 8)}...${value.slice(-4)}`;
}

function summarizeRuntimeMode(value?: string): string {
  if (!value) {
    return "loading";
  }
  if (value === "nvidia_ready_openrouter_degraded") {
    return "Kimi ready";
  }
  if (value === "deterministic_fallback_only") {
    return "Local fallback";
  }
  return humanizeLabel(value);
}

function renderMessageContent(content: string) {
  const blocks = content
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean);

  return blocks.map((block, index) => {
    const lines = block
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);

    if (lines.length > 0 && lines.every((line) => /^[-*]\s+/.test(line))) {
      return (
        <ul className="message-list" key={`block-${index}`}>
          {lines.map((line) => (
            <li key={line}>{line.replace(/^[-*]\s+/, "")}</li>
          ))}
        </ul>
      );
    }

    if (lines.length > 0 && lines.every((line) => /^\d+\.\s+/.test(line))) {
      return (
        <ol className="message-list ordered" key={`block-${index}`}>
          {lines.map((line) => (
            <li key={line}>{line.replace(/^\d+\.\s+/, "")}</li>
          ))}
        </ol>
      );
    }

    return <p key={`block-${index}`}>{block}</p>;
  });
}

function parsePrompt(prompt: string): AgentRunRequest {
  const trimmed = prompt.trim();
  const normalized = trimmed.toLowerCase();
  if (normalized.startsWith("/refresh")) {
    return { automation: "refresh_opportunity", prompt: trimmed.replace(/^\/refresh\s*/i, "") || "Refresh this opportunity." };
  }
  if (normalized.startsWith("/review")) {
    return { automation: "review_draft", prompt: trimmed.replace(/^\/review\s*/i, "") || "Review this draft." };
  }
  if (normalized.startsWith("/handoff")) {
    return { automation: "build_handoff", prompt: trimmed.replace(/^\/handoff\s*/i, "") || "Generate a closed-won handoff." };
  }
  if (normalized.startsWith("/summarize")) {
    return { automation: "summarize_account", prompt: trimmed.replace(/^\/summarize\s*/i, "") || "Summarize this account." };
  }
  return { prompt: trimmed };
}

function isDiscoveryPrompt(prompt: string, hasAccount: boolean): boolean {
  if (hasAccount) {
    return false;
  }
  const normalized = prompt.toLowerCase();
  const discoveryMarkers = [
    "find interested",
    "interested parties",
    "interested org",
    "interested compan",
    "prospects",
    "prospecting",
    "search the interested",
    "search interested",
    "find companies",
    "find banks",
    "find fintech",
    "find leads"
  ];
  return discoveryMarkers.some((marker) => normalized.includes(marker));
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function welcomeMessage(accountId?: string, draftId?: string): ChatMessage {
  const contextBits = [accountId ? `account ${accountId}` : null, draftId ? `draft ${draftId}` : null].filter(Boolean);
  return {
    id: "welcome",
    role: "assistant",
    content:
      "Ask for account triage, stakeholder-specific messaging, compliance review, or activation handoff guidance. I stay grounded in the current Blostem workspace and attached evidence.",
    meta: contextBits.length > 0 ? `Attached context: ${contextBits.join(" | ")}` : "No page context is currently attached."
  };
}

export function AgentSidebar({ accountId, draftId }: AgentSidebarProps) {
  const [prompt, setPrompt] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([welcomeMessage(accountId, draftId)]);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [isPending, setIsPending] = useState(false);
  const [pendingLabel, setPendingLabel] = useState("Working on that...");
  const [error, setError] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(true);
  const panelRef = useRef<HTMLElement | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const showStarters = messages.length <= 1;

  useEffect(() => {
    let active = true;
    void getSystemStatus()
      .then((nextStatus) => {
        if (active) {
          setStatus(nextStatus);
        }
      })
      .catch((nextError: Error) => {
        if (active) {
          setError(nextError.message);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages]);

  function appendAssistantFromResult(result: AgentResult) {
    setMessages((current) => [
      ...current,
      {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: result.summary,
        meta: `${result.route.provider}:${result.route.model} | ${result.automation ?? "chat"} | ${result.used_live_model ? "live" : "not live"}`,
        actions: result.suggested_actions,
        citations: result.citations
      }
    ]);
  }

  function appendDiscoveryResult(result: DiscoverySearchResponse) {
    const rankedLines =
      result.candidates.length > 0
        ? result.candidates
            .slice(0, 5)
            .map(
              (candidate, index) =>
                `${index + 1}. ${candidate.name} (${candidate.segment}) - interest ${candidate.interest_score}, fit ${candidate.fit_score}, freshness ${candidate.freshness_score}`
            )
            .join("\n")
        : "No signal-backed candidates matched the current discovery prompt.";

    const suggestedActions =
      result.candidates.length > 0
        ? [
            "Open the Account Queue to review the ranked discovery results.",
            `Use Add to queue on ${result.candidates[0].name} if you want to convert it into a tracked account.`,
            "Refine the prompt with a tighter trigger or geography if you want a narrower list."
          ]
        : [
            "Adjust the prompt to include a clearer BFSI trigger such as fraud, breach, compliance, or onboarding.",
            "Verify that a matching product context exists for the product name you mentioned."
          ];

    setMessages((current) => [
      ...current,
      {
        id: `discovery-${Date.now()}`,
        role: "assistant",
        content: `Discovery searched ${result.product_context_name} and ranked ${result.candidates.length} candidates.\n\n${rankedLines}`,
        meta: `${result.route.provider}:${result.route.model} | discovery search`,
        actions: suggestedActions,
        citations: result.candidates.flatMap((candidate) => candidate.citations).slice(0, 3)
      }
    ]);
  }

  function appendErrorMessage(message: string) {
    setMessages((current) => [
      ...current,
      {
        id: `error-${Date.now()}`,
        role: "assistant",
        content: message,
        meta: "The backend rejected the request.",
        tone: "error"
      }
    ]);
  }

  async function execute(nextPrompt: string) {
    const trimmed = nextPrompt.trim();
    if (!trimmed) {
      return;
    }
    const request = parsePrompt(trimmed);
    setError(null);
    setIsPending(true);
    setMessages((current) => [
      ...current,
      {
        id: `user-${Date.now()}`,
        role: "user",
        content: trimmed
      }
    ]);
    setPendingLabel("Working on that...");
    try {
      if (isDiscoveryPrompt(trimmed, Boolean(accountId))) {
        setPendingLabel("Searching for signal-backed interested organizations...");
        const discovery = await searchDiscovery({ prompt: trimmed, limit: 8 });
        appendDiscoveryResult(discovery);
        setPrompt("");
        return;
      }

      const job = await createAgentJob({
        ...request,
        account_id: request.account_id ?? accountId,
        draft_id: request.draft_id ?? draftId
      });
      setPendingLabel(job.progress_message || "Queued...");

      for (let attempt = 0; attempt < 240; attempt += 1) {
        const current = await getAgentJob(job.id);
        setPendingLabel(current.progress_message || `Job ${current.status}...`);
        if (current.status === "completed" && current.result) {
          appendAssistantFromResult(current.result);
          setPrompt("");
          return;
        }
        if (current.status === "failed") {
          throw new Error(current.error_message || "The background job failed.");
        }
        await sleep(2000);
      }
      throw new Error("The request is still running. Please retry in a moment.");
    } catch (nextError) {
      const message = nextError instanceof Error ? nextError.message : "Request failed.";
      setError(message);
      appendErrorMessage(message);
    } finally {
      setIsPending(false);
      setPendingLabel("Working on that...");
    }
  }

  return (
    <>
      <button className={`agent-launcher ${isOpen ? "agent-launcher-hidden" : ""}`} onClick={() => setIsOpen(true)} type="button">
        <span className="agent-launcher-label">Copilot</span>
        <span className="agent-launcher-state">{summarizeRuntimeMode(status?.llm_mode)}</span>
      </button>
      <aside className={`agent-rail ${isOpen ? "agent-rail-open" : "agent-rail-collapsed"}`}>
        <section className="agent-panel" ref={panelRef}>
          <header className="agent-header">
            <div className="agent-header-copy">
              <p className="eyebrow">Blostem Copilot</p>
              <h3>Ask or automate</h3>
              <p className="muted">Right-rail workspace for triage, drafting, review, and handoff actions.</p>
            </div>
            <div className="agent-header-actions">
              <span className="pill neutral">{summarizeRuntimeMode(status?.llm_mode)}</span>
              <button className="rail-close" onClick={() => setIsOpen(false)} type="button" aria-label="Collapse sidebar">
                Close
              </button>
            </div>
          </header>

          <div className="context-row">
            {accountId ? <span className="context-chip">Account {compactIdentifier(accountId)}</span> : null}
            {draftId ? <span className="context-chip">Draft {compactIdentifier(draftId)}</span> : null}
            {!accountId && !draftId ? <span className="context-chip">General context</span> : null}
          </div>

          <section className="sidebar-section stack-sm">
            <div className="section-kicker">
              <span>Workflow shortcuts</span>
            </div>
            <div className="quick-commands">
              {quickCommands.map((command) => {
                const disabled =
                  isPending ||
                  (command.requires === "account" && !accountId) ||
                  (command.requires === "draft" && !draftId);
                return (
                  <button className="quick-command" disabled={disabled} key={command.label} onClick={() => void execute(command.prompt)} type="button">
                    {command.label}
                  </button>
                );
              })}
            </div>
          </section>

          {showStarters ? (
            <section className="sidebar-section stack-sm">
              <div className="section-kicker">
                <span>Prompt ideas</span>
              </div>
              <div className="starter-grid">
                {starterPrompts.map((starter) => (
                  <button className="starter-card" disabled={isPending} key={starter} onClick={() => void execute(starter)} type="button">
                    {starter}
                  </button>
                ))}
              </div>
            </section>
          ) : null}

          <div className="chat-thread">
            {messages.map((message) => (
              <article
                className={`chat-message role-${message.role} ${message.tone === "error" ? "message-error" : ""}`}
                key={message.id}
              >
                <div className="chat-role">{message.role === "user" ? "You" : message.role === "assistant" ? "Copilot" : "System"}</div>
                <div className="message-body">{renderMessageContent(message.content)}</div>
                {message.actions?.length ? (
                  <section className="message-section">
                    <div className="message-section-label">Suggested actions</div>
                    <ul className="message-list">
                      {message.actions.map((action) => (
                        <li key={action}>{action}</li>
                      ))}
                    </ul>
                  </section>
                ) : null}
                {message.citations?.length ? (
                  <section className="message-section">
                    <div className="message-section-label">Sources</div>
                    <div className="message-citations">
                      {message.citations.slice(0, 3).map((citation) => (
                        <a
                          className="mini-citation"
                          href={citation.source_url}
                          key={`${citation.label}-${citation.claim}`}
                          rel="noreferrer"
                          target="_blank"
                        >
                          {citation.label}
                        </a>
                      ))}
                    </div>
                  </section>
                ) : null}
                {message.meta ? (
                  <footer className="message-footer">
                    <small className="message-meta">{message.meta}</small>
                  </footer>
                ) : null}
              </article>
            ))}
            {isPending ? (
              <article className="chat-message role-assistant">
                <div className="chat-role">Copilot</div>
                <div className="message-body">
                  <p>{pendingLabel}</p>
                </div>
              </article>
            ) : null}
            <div ref={endRef} />
          </div>

          <details className="runtime-details">
            <summary>Runtime status</summary>
            {status ? (
              <div className="runtime-body">
                <div className="runtime-stats">
                  <span>{humanizeLabel(status.database_mode)}</span>
                  <span>{humanizeLabel(status.crm_mode)}</span>
                  <span>{status.account_count} accounts</span>
                  <span>{status.product_context_count} product contexts</span>
                </div>
                <div className="stack-sm">
                  {Object.entries(status.integrations).map(([key, value]) => (
                    <div className="status-row" key={key}>
                      <strong>{humanizeLabel(key)}</strong>
                      <p>{value}</p>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="muted">Loading runtime status...</p>
            )}
          </details>

          {status && status.account_count === 0 ? (
            <div className="empty-hint">
              <p>No live data has been created yet.</p>
              <p>
                Use the backend docs at <a href={`${getApiBaseUrl()}/docs`}>{getApiBaseUrl()}/docs</a> to create product contexts,
                accounts, contacts, and signals.
              </p>
            </div>
          ) : null}

          <div className="composer">
            <textarea
              className="agent-textarea"
              onChange={(event) => setPrompt(event.target.value)}
              onKeyDown={(event) => {
                if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                  event.preventDefault();
                  execute(prompt);
                }
              }}
              placeholder="Ask about the current account, or use /refresh, /review, /handoff, /summarize"
              rows={4}
              value={prompt}
            />
            <div className="composer-row">
              <span className="muted">Ctrl/Cmd + Enter to send</span>
              <button className="primary-button" disabled={isPending || prompt.trim().length === 0} onClick={() => void execute(prompt)} type="button">
                Send
              </button>
            </div>
            {error ? <p className="error-text">{error}</p> : null}
          </div>
        </section>
      </aside>
    </>
  );
}
