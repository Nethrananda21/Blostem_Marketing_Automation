import type { RationaleStep } from "../lib/types";

export function RationaleList({ steps }: { steps: RationaleStep[] }) {
  return (
    <div className="stack-sm">
      {steps.map((step) => (
        <div className="rationale" key={step.title}>
          <div className="rationale-head">
            <strong>{step.title}</strong>
            <span>{Math.round(step.weight * 100)}%</span>
          </div>
          <p>{step.detail}</p>
        </div>
      ))}
    </div>
  );
}

