import { CloudRain, type LucideIcon, Satellite, ShieldCheck } from "lucide-react";

import { ATTRIBUTION, STATUS, STEPS, type Step } from "./content.ts";
import { Dotted } from "./Dotted.tsx";
import { FollowToggle } from "./follow/FollowToggle.tsx";

/** Icon per step. */
const STEP_ICONS: Record<Step["id"], LucideIcon> = {
  observe: Satellite,
  explain: CloudRain,
  verify: ShieldCheck,
};

/**
 * The hero's bottom row: the three-step strip on the text column, "Follow satellite" and the status
 * chip on the right, and the data attribution under the strip.
 *
 * @returns The bottom row.
 */
export function Footer() {
  return (
    <div className="hero-foot">
      <div className="hero-foot__row">
        <ol className="hero-steps">
          {STEPS.map((step) => {
            const Icon = STEP_ICONS[step.id];
            return (
              <li key={step.id} className={`hero-step hero-step--${step.id}`}>
                <p className="hero-step__head">
                  <Icon
                    className="hero-step__icon"
                    size={18}
                    strokeWidth={1.5}
                    nonScalingStroke
                    aria-hidden="true"
                  />
                  <span className="hero-step__label">
                    <span className="hero-step__number" aria-hidden="true">
                      {step.number}
                    </span>{" "}
                    {step.label}
                  </span>
                </p>
                <p className="hero-step__desc">{step.description}</p>
              </li>
            );
          })}
        </ol>
        <FollowToggle />
        <p className="hero-chip hero-ui__glass">
          <span className="hero-chip__dot" aria-hidden="true" />
          <span className="hero-chip__text">
            <Dotted items={STATUS} />
          </span>
        </p>
      </div>
      <p className="hero-attribution">{ATTRIBUTION}</p>
    </div>
  );
}
