import type { Citation } from "../lib/types";

export function CitationList({ citations }: { citations: Citation[] }) {
  return (
    <div className="stack-sm">
      {citations.map((citation) => (
        <a className="citation" href={citation.source_url} key={`${citation.label}-${citation.claim}`}>
          <span className="citation-label">{citation.label}</span>
          <strong>{citation.claim}</strong>
          {citation.excerpt ? <p>{citation.excerpt}</p> : null}
        </a>
      ))}
    </div>
  );
}

