import { CASE_COPY } from "../content.ts";

/**
 * The observation's record: scene, processing version, parameters and anchored root. In this demo
 * every value is a placeholder and nothing is anchored, so the panel says so, and "Recompute this
 * observation" stays disabled. Phones show its heading line only.
 *
 * @returns The record panel.
 */
export function RecordPanel() {
  const { record } = CASE_COPY;
  const rows = [
    { label: record.scene, value: record.placeholder },
    { label: record.version, value: record.placeholder },
    { label: record.parameters, value: record.placeholder },
    { label: record.root, value: record.notAnchored },
  ];
  return (
    <section className="case-panel case-record case-glass" aria-labelledby="case-record-title">
      <h2 className="case-record__title" id="case-record-title">
        {record.title}
        <span className="case-record__note">{record.note}</span>
      </h2>
      <dl className="case-record__rows">
        {rows.map((row) => (
          <div className="case-record__row" key={row.label}>
            <dt>{row.label}</dt>
            <dd>{row.value}</dd>
          </div>
        ))}
      </dl>
      <button
        type="button"
        className="case-btn case-btn--ghost case-record__recompute"
        disabled
        aria-describedby="case-recompute-hint"
      >
        {record.recompute}
      </button>
      <p className="case-record__hint" id="case-recompute-hint">
        {record.recomputeHint}
      </p>
    </section>
  );
}
