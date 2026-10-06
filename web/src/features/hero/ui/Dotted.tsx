import { Fragment } from "react";

/** Props of {@link Dotted}. */
export interface DottedProps {
  /** Items, in reading order. */
  readonly items: readonly string[];
}

/**
 * Inline items separated by middle dots. The dots are hidden from screen readers, which read the
 * items as a plain sequence.
 *
 * @returns The items and their separators.
 */
export function Dotted({ items }: DottedProps) {
  return items.map((item, index) => (
    <Fragment key={item}>
      {index > 0 ? (
        <>
          {" "}
          <span aria-hidden="true">·</span>{" "}
        </>
      ) : null}
      {item}
    </Fragment>
  ));
}
