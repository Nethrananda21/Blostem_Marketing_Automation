import type { ComplianceReceipt } from "../lib/types";

export function CompliancePanel({ receipt }: { receipt: ComplianceReceipt | null | undefined }) {
  if (!receipt) {
    return (
      <section className="card stack-sm">
        <h3>Compliance Receipt</h3>
        <p>No compliance review is available yet.</p>
      </section>
    );
  }

  return (
    <section className="card stack-sm">
      <div className="section-head">
        <h3>Compliance Receipt</h3>
        <span className={receipt.passed ? "pill success" : "pill danger"}>
          {receipt.passed ? "Pass" : "Needs revision"}
        </span>
      </div>
      <p className="muted">{receipt.route.reason}</p>
      {receipt.issues.length > 0 ? (
        <ul className="plain-list">
          {receipt.issues.map((issue) => (
            <li key={issue}>{issue}</li>
          ))}
        </ul>
      ) : (
        <p>No blocking issues were found.</p>
      )}
      <div className="stack-sm">
        {receipt.claim_checks.map((check) => (
          <div className="claim-check" key={check.sentence}>
            <span className={check.supported ? "pill success" : "pill danger"}>
              {check.sentence_type === "boilerplate" ? "Boilerplate" : "Claim"}
            </span>
            <p>{check.sentence}</p>
            <small>{check.reason}</small>
          </div>
        ))}
      </div>
    </section>
  );
}

