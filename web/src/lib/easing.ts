// Easing curves shared by the hero dive and the map flight.

/** An easing curve: maps progress 0..1 to eased progress (0 → 0, 1 → 1). */
export type Easing = (t: number) => number;

/**
 * A CSS-style cubic Bézier easing, `cubic-bezier(x1, y1, x2, y2)`, solved for x with Newton steps
 * and a bisection fallback.
 *
 * @param x1 - First control point, x (0..1).
 * @param y1 - First control point, y.
 * @param x2 - Second control point, x (0..1).
 * @param y2 - Second control point, y.
 * @returns The easing function.
 */
export function cubicBezier(x1: number, y1: number, x2: number, y2: number): Easing {
  // Polynomial coefficients of B(s) = ((a·s + b)·s + c)·s for each axis.
  const cx = 3 * x1;
  const bx = 3 * (x2 - x1) - cx;
  const ax = 1 - cx - bx;
  const cy = 3 * y1;
  const by = 3 * (y2 - y1) - cy;
  const ay = 1 - cy - by;
  const sampleX = (s: number) => ((ax * s + bx) * s + cx) * s;
  const sampleY = (s: number) => ((ay * s + by) * s + cy) * s;
  const slopeX = (s: number) => (3 * ax * s + 2 * bx) * s + cx;

  const solveS = (x: number) => {
    let s = x;
    for (let i = 0; i < 8; i += 1) {
      const error = sampleX(s) - x;
      const slope = slopeX(s);
      if (Math.abs(error) < 1e-7) {
        return s;
      }
      if (Math.abs(slope) < 1e-6) {
        break;
      }
      s -= error / slope;
    }
    let low = 0;
    let high = 1;
    s = x;
    for (let i = 0; i < 40 && high - low > 1e-7; i += 1) {
      if (sampleX(s) < x) {
        low = s;
      } else {
        high = s;
      }
      s = (low + high) / 2;
    }
    return s;
  };

  return (t: number) => {
    if (t <= 0) {
      return 0;
    }
    if (t >= 1) {
      return 1;
    }
    return sampleY(solveS(t));
  };
}
