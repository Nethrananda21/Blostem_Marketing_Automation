"use client";

import { useRouter } from "next/navigation";
import { startTransition, useState } from "react";

import { ApiError, approveDraft, editDraft, rejectDraft } from "../lib/api";

export function DraftActions({
  draftId,
  initialStatus,
  initialBody,
  persona,
}: {
  draftId: string;
  initialStatus: string;
  initialBody: string;
  persona: string;
}) {
  const router = useRouter();
  const [status, setStatus] = useState(initialStatus);
  const [editedBody, setEditedBody] = useState(initialBody);
  const [isEditing, setIsEditing] = useState(false);
  const [notes, setNotes] = useState("");
  const [reviewerRole, setReviewerRole] = useState("rep");
  const [isApproving, setIsApproving] = useState(false);
  const [isRejecting, setIsRejecting] = useState(false);
  const [isSavingEdit, setIsSavingEdit] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [emailSent, setEmailSent] = useState(false);

  const isTerminal = status === "approved" || status === "rejected";

  function handleApprove() {
    if (!reviewerRole.trim()) return;
    setError(null);
    setIsApproving(true);
    startTransition(() => {
      void approveDraft(draftId, reviewerRole, notes)
        .then(() => {
          setStatus("approved");
          setEmailSent(true);
          router.refresh();
        })
        .catch((err: Error) => {
          setError(err instanceof ApiError ? err.message : "Approval failed.");
        })
        .finally(() => setIsApproving(false));
    });
  }

  function handleReject() {
    if (!reviewerRole.trim()) return;
    setError(null);
    setIsRejecting(true);
    startTransition(() => {
      void rejectDraft(draftId, reviewerRole, notes)
        .then(() => {
          setStatus("rejected");
          router.refresh();
        })
        .catch((err: Error) => {
          setError(err instanceof ApiError ? err.message : "Rejection failed.");
        })
        .finally(() => setIsRejecting(false));
    });
  }

  function handleSaveEdit() {
    setError(null);
    setIsSavingEdit(true);
    startTransition(() => {
      void editDraft(draftId, editedBody)
        .then((result) => {
          setStatus(result.status);
          setIsEditing(false);
          router.refresh();
        })
        .catch((err: Error) => {
          setError(err instanceof ApiError ? err.message : "Save failed.");
        })
        .finally(() => setIsSavingEdit(false));
    });
  }

  if (isTerminal && !emailSent) {
    return (
      <div className={`action-result-banner ${status === "approved" ? "banner-success" : "banner-danger"}`}>
        <span className="eyebrow">{status === "approved" ? "✓ Approved" : "✗ Rejected"}</span>
        <p>This draft has been {status}.</p>
      </div>
    );
  }

  if (status === "approved" && emailSent) {
    return (
      <div className="action-result-banner banner-success">
        <span className="eyebrow">✓ Approved & sent</span>
        <p>
          Email dispatched to <strong>nethranandareddy9@gmail.com</strong>
          {" "}(demo override — real recipient: <em>{persona}</em> contact).
        </p>
      </div>
    );
  }

  return (
    <div className="draft-actions-panel stack-sm">
      {/* Reviewer identity */}
      <div className="draft-actions-row">
        <label className="field-label compact-field">
          Reviewer role
          <select
            className="agent-select"
            onChange={(e) => setReviewerRole(e.target.value)}
            value={reviewerRole}
          >
            <option value="rep">Sales Rep</option>
            <option value="manager">Sales Manager</option>
            <option value="compliance">Compliance Officer</option>
            <option value="cto">CTO</option>
          </select>
        </label>

        <label className="field-label" style={{ flex: 1 }}>
          Notes (optional)
          <input
            className="agent-input"
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Add review notes…"
            type="text"
            value={notes}
          />
        </label>
      </div>

      {error ? <p className="error-text">{error}</p> : null}

      {/* Edit toggle */}
      {isEditing ? (
        <div className="stack-sm">
          <label className="field-label">
            Edit draft body
            <textarea
              className="agent-textarea"
              onChange={(e) => setEditedBody(e.target.value)}
              rows={12}
              value={editedBody}
            />
          </label>
          <div className="actions">
            <button
              className="primary-button"
              disabled={isSavingEdit}
              onClick={handleSaveEdit}
              type="button"
            >
              {isSavingEdit ? "Saving & re-checking…" : "Save & re-check compliance"}
            </button>
            <button
              className="ghost-button"
              onClick={() => { setIsEditing(false); setEditedBody(initialBody); }}
              type="button"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="actions">
          <button
            className="primary-button approve-btn"
            disabled={isApproving || isRejecting}
            onClick={handleApprove}
            type="button"
          >
            {isApproving ? "Approving & sending…" : "✓ Approve & send email"}
          </button>
          <button
            className="ghost-button reject-btn"
            disabled={isApproving || isRejecting}
            onClick={handleReject}
            type="button"
          >
            {isRejecting ? "Rejecting…" : "✗ Reject"}
          </button>
          <button
            className="ghost-button"
            onClick={() => setIsEditing(true)}
            type="button"
          >
            Edit draft
          </button>
        </div>
      )}
    </div>
  );
}
