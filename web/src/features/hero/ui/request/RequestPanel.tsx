// "Request a study reach": a form that sends and stores nothing. Submitting only shows a summary of
// what was entered, held in React state; there is no network call and no storage of any kind.
import "./request.css";

import { ArrowLeft } from "lucide-react";
import { useEffect, useId, useRef, useState, type Ref, type SubmitEvent } from "react";

import { IN_SITU_ANSWERS, PURPOSES, REQUEST } from "./content.ts";
import {
  EMPTY_REQUEST,
  parseCoordinate,
  validateRequest,
  type RequestErrors,
  type RequestField,
  type RequestValues,
} from "./validate.ts";

/** Props of {@link RequestPanel}. */
export interface RequestPanelProps {
  /** Id of the heading, which labels the hero section while this screen shows. */
  readonly titleId: string;
  /** Receives the heading (focus moves to it when the screen opens). */
  readonly headingRef?: Ref<HTMLHeadingElement>;
  /** Back to the cases screen. */
  readonly onBack: () => void;
  /** Announces a change politely (the overlay's live region). */
  readonly onAnnounce?: (message: string) => void;
}

// Field order, for the error summary.
const FIELD_ORDER: readonly RequestField[] = [
  "reachName",
  "river",
  "location",
  "latitude",
  "longitude",
  "purpose",
  "inSitu",
  "notes",
];

function check(values: RequestValues): RequestErrors {
  return validateRequest(values, REQUEST.errors, PURPOSES, IN_SITU_ANSWERS);
}

/**
 * The request form and, once submitted, the summary of the request. Validation is accessible: each
 * invalid field is marked and described by its message, and an error summary, which takes focus,
 * links to each field.
 *
 * @returns The request panel.
 */
export function RequestPanel({ titleId, headingRef, onBack, onAnnounce }: RequestPanelProps) {
  const [values, setValues] = useState<RequestValues>(EMPTY_REQUEST);
  const [errors, setErrors] = useState<RequestErrors>({});
  const [attempted, setAttempted] = useState(false);
  const [submitted, setSubmitted] = useState<RequestValues | null>(null);
  const prefix = useId();
  const summaryRef = useRef<HTMLDivElement>(null);
  const doneRef = useRef<HTMLHeadingElement>(null);
  // Where focus goes after the next render: the error summary, the summary of the request, or the
  // first field (a new request).
  const pendingFocus = useRef<"errors" | "done" | "first" | null>(null);

  const fieldId = (field: RequestField) => `${prefix}-${field}`;
  const errorId = (field: RequestField) => `${prefix}-${field}-error`;
  const hintId = (field: RequestField) => `${prefix}-${field}-hint`;
  const errorList = FIELD_ORDER.flatMap((field) => {
    const message = errors[field];
    return message === undefined ? [] : [{ field, message }];
  });

  useEffect(() => {
    const target = pendingFocus.current;
    pendingFocus.current = null;
    if (target === "errors") {
      summaryRef.current?.focus({ preventScroll: false });
    } else if (target === "done") {
      doneRef.current?.focus({ preventScroll: false });
    } else if (target === "first") {
      document.getElementById(fieldId("reachName"))?.focus();
    }
  });

  const update = (field: RequestField, value: string) => {
    const next = { ...values, [field]: value };
    setValues(next);
    // After a failed submit, messages follow the edits.
    if (attempted) {
      setErrors(check(next));
    }
  };

  const onSubmit = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found = check(values);
    setAttempted(true);
    setErrors(found);
    if (Object.keys(found).length > 0) {
      pendingFocus.current = "errors";
      return;
    }
    setSubmitted(values);
    pendingFocus.current = "done";
    onAnnounce?.(REQUEST.announceDone);
  };

  const again = () => {
    setValues(EMPTY_REQUEST);
    setErrors({});
    setAttempted(false);
    setSubmitted(null);
    pendingFocus.current = "first";
  };

  // aria-describedby for a field: its hint, then its message when invalid.
  const describedBy = (field: RequestField, hint = false) =>
    [hint ? hintId(field) : null, errors[field] === undefined ? null : errorId(field)]
      .filter((id) => id !== null)
      .join(" ") || undefined;

  const message = (field: RequestField) =>
    errors[field] === undefined ? null : (
      <p className="hero-request__error" id={errorId(field)}>
        {errors[field]}
      </p>
    );

  const { fields } = REQUEST;
  const textField = (
    field: "reachName" | "river" | "location",
    required: boolean,
    hint?: string,
  ) => (
    <div className="hero-request__field" data-invalid={errors[field] !== undefined}>
      <label className="hero-request__label" htmlFor={fieldId(field)}>
        {fields[field].label}
        <span className="hero-request__marker">
          {required ? REQUEST.required : REQUEST.optional}
        </span>
      </label>
      {hint === undefined ? null : (
        <p className="hero-request__hint" id={hintId(field)}>
          {hint}
        </p>
      )}
      <input
        id={fieldId(field)}
        className="hero-request__input"
        type="text"
        value={values[field]}
        onChange={(event) => {
          update(field, event.target.value);
        }}
        aria-required={required}
        aria-invalid={errors[field] !== undefined}
        aria-describedby={describedBy(field, hint !== undefined)}
        maxLength={160}
      />
      {message(field)}
    </div>
  );

  return (
    <section className="hero-panel hero-request hero-ui__glass" aria-labelledby={titleId}>
      <div className="hero-panel__head">
        <h1 ref={headingRef} className="hero-panel__title" id={titleId} tabIndex={-1}>
          {REQUEST.heading}
        </h1>
        <button
          type="button"
          className="hero-panel__back"
          onClick={onBack}
          aria-label={REQUEST.backLabel}
        >
          <ArrowLeft size={15} strokeWidth={1.75} nonScalingStroke aria-hidden="true" />
          {REQUEST.back}
        </button>
        <p className="hero-panel__note hero-request__demo">{REQUEST.demoOnly}</p>
      </div>

      {submitted === null ? (
        // autoComplete off: the browser keeps no history of what was typed either.
        <form className="hero-request__form" onSubmit={onSubmit} noValidate autoComplete="off">
          {attempted && errorList.length > 0 ? (
            <div
              ref={summaryRef}
              className="hero-request__summary"
              tabIndex={-1}
              role="group"
              aria-labelledby={`${prefix}-summary`}
            >
              <h2 className="hero-request__summary-title" id={`${prefix}-summary`}>
                {REQUEST.errors.summary(errorList.length)}
              </h2>
              <ul>
                {errorList.map(({ field, message: text }) => (
                  <li key={field}>
                    <a
                      href={`#${fieldId(field)}`}
                      onClick={(event) => {
                        event.preventDefault();
                        document.getElementById(fieldId(field))?.focus();
                      }}
                    >
                      {text}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {textField("reachName", true, fields.reachName.hint)}
          {textField("river", true)}
          {textField("location", false, fields.location.hint)}

          <fieldset
            className="hero-request__fieldset"
            aria-describedby={hintId("latitude")}
            data-invalid={errors.latitude !== undefined || errors.longitude !== undefined}
          >
            <legend className="hero-request__label">
              {fields.coordinates.legend}
              <span className="hero-request__marker">{REQUEST.optional}</span>
            </legend>
            <p className="hero-request__hint" id={hintId("latitude")}>
              {fields.coordinates.hint}
            </p>
            <div className="hero-request__pair">
              {(["latitude", "longitude"] as const).map((field) => (
                <div key={field} className="hero-request__field">
                  <label className="hero-request__sublabel" htmlFor={fieldId(field)}>
                    {fields[field].label}
                  </label>
                  <input
                    id={fieldId(field)}
                    className="hero-request__input"
                    type="text"
                    inputMode="decimal"
                    value={values[field]}
                    onChange={(event) => {
                      update(field, event.target.value);
                    }}
                    aria-invalid={errors[field] !== undefined}
                    aria-describedby={describedBy(field)}
                    maxLength={24}
                  />
                </div>
              ))}
            </div>
            {message("latitude")}
            {message("longitude")}
          </fieldset>

          <div className="hero-request__field" data-invalid={errors.purpose !== undefined}>
            <label className="hero-request__label" htmlFor={fieldId("purpose")}>
              {fields.purpose.label}
              <span className="hero-request__marker">{REQUEST.required}</span>
            </label>
            <select
              id={fieldId("purpose")}
              className="hero-request__input hero-request__select"
              value={values.purpose}
              onChange={(event) => {
                update("purpose", event.target.value);
              }}
              aria-required="true"
              aria-invalid={errors.purpose !== undefined}
              aria-describedby={describedBy("purpose")}
            >
              <option value="" disabled>
                {fields.purpose.placeholder}
              </option>
              {PURPOSES.map((purpose) => (
                <option key={purpose} value={purpose}>
                  {purpose}
                </option>
              ))}
            </select>
            {message("purpose")}
          </div>

          <fieldset className="hero-request__fieldset" data-invalid={errors.inSitu !== undefined}>
            <legend className="hero-request__label">
              {fields.inSitu.legend}
              <span className="hero-request__marker">{REQUEST.required}</span>
            </legend>
            <div className="hero-request__choices">
              {IN_SITU_ANSWERS.map((answer, index) => (
                <label key={answer} className="hero-request__choice">
                  <input
                    // The first option carries the field's id, so the error summary can focus it.
                    id={index === 0 ? fieldId("inSitu") : undefined}
                    type="radio"
                    name={`${prefix}-inSitu`}
                    value={answer}
                    checked={values.inSitu === answer}
                    onChange={() => {
                      update("inSitu", answer);
                    }}
                    aria-describedby={describedBy("inSitu")}
                  />
                  {answer}
                </label>
              ))}
            </div>
            {message("inSitu")}
          </fieldset>

          <div className="hero-request__field">
            <label className="hero-request__label" htmlFor={fieldId("notes")}>
              {fields.notes.label}
              <span className="hero-request__marker">{REQUEST.optional}</span>
            </label>
            <textarea
              id={fieldId("notes")}
              className="hero-request__input hero-request__textarea"
              rows={3}
              value={values.notes}
              onChange={(event) => {
                update("notes", event.target.value);
              }}
              maxLength={1000}
            />
          </div>

          <button type="submit" className="hero-btn hero-btn--solid hero-request__submit">
            {REQUEST.submit}
          </button>
        </form>
      ) : (
        <RequestSummary values={submitted} headingRef={doneRef} onAgain={again} onBack={onBack} />
      )}
    </section>
  );
}

/** Props of {@link RequestSummary}. */
interface RequestSummaryProps {
  readonly values: RequestValues;
  readonly headingRef: Ref<HTMLHeadingElement>;
  readonly onAgain: () => void;
  readonly onBack: () => void;
}

// What was entered, read back, with what a real deployment would do with it.
function RequestSummary({ values, headingRef, onAgain, onBack }: RequestSummaryProps) {
  const { confirmation, fields } = REQUEST;
  const latitude = parseCoordinate(values.latitude, 90);
  const longitude = parseCoordinate(values.longitude, 180);
  const orNone = (text: string) => (text.trim() === "" ? confirmation.none : text.trim());
  const rows = [
    { label: fields.reachName.label, value: values.reachName.trim() },
    { label: fields.river.label, value: values.river.trim() },
    { label: fields.location.label, value: orNone(values.location) },
    {
      label: confirmation.coordinates,
      value:
        latitude === null || longitude === null
          ? confirmation.none
          : `${String(latitude)}, ${String(longitude)}`,
    },
    { label: fields.purpose.label, value: values.purpose },
    { label: fields.inSitu.legend, value: values.inSitu },
    { label: fields.notes.label, value: orNone(values.notes) },
  ];
  return (
    <div className="hero-request__done">
      <h2 ref={headingRef} className="hero-request__done-title" tabIndex={-1}>
        {confirmation.heading}
      </h2>
      <dl className="hero-request__readback" aria-label={confirmation.summaryLabel}>
        {rows.map((row) => (
          <div key={row.label} className="hero-request__readback-row">
            <dt>{row.label}</dt>
            <dd>{row.value}</dd>
          </div>
        ))}
      </dl>
      <p className="hero-request__body">{confirmation.body}</p>
      <div className="hero-request__actions">
        <button type="button" className="hero-btn hero-btn--solid" onClick={onAgain}>
          {confirmation.again}
        </button>
        <button type="button" className="hero-btn hero-btn--ghost" onClick={onBack}>
          {confirmation.back}
        </button>
      </div>
    </div>
  );
}
