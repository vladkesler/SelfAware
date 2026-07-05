/**
 * LoopDiagram — generate/deploy/observe/validate/register rendered as a ring
 * with a continuously traveling phosphor dot, closing back to "generate".
 * Decorative: the stage names are already stated in the surrounding copy, so
 * this is aria-hidden (same treatment as TeaserStream). Motion is CSS-only
 * (base.css) and freezes under prefers-reduced-motion without losing legibility.
 *
 * Stage positions and glow delays are both derived from one angle per stage
 * so they can't drift apart. `offset-path: circle()`'s 0% point is the
 * rightmost point of the circle (3 o'clock), not the top — confirmed
 * empirically — so ANGLE_FROM_3_OCLOCK feeds both the label's (top, left) %
 * position and the moment its glow keyframe should fire.
 */
const CYCLE_S = 6.5;
const RADIUS_PCT = 38;

const STAGES = ['generate', 'deploy', 'observe', 'validate', 'register'];

// One point per stage, evenly spaced, starting at the top and going clockwise.
const ANGLE_FROM_3_OCLOCK_DEG = STAGES.map((_, i) => -90 + i * (360 / STAGES.length));

const STAGE_LAYOUT = ANGLE_FROM_3_OCLOCK_DEG.map((deg) => {
  const rad = (deg * Math.PI) / 180;
  const offsetDistance = ((deg % 360) + 360) % 360 / 360;
  return {
    top: 50 + RADIUS_PCT * Math.sin(rad),
    left: 50 + RADIUS_PCT * Math.cos(rad),
    delayS: offsetDistance * CYCLE_S,
  };
});

export function LoopDiagram() {
  return (
    <div className="loop-diagram" aria-hidden="true">
      <div className="loop-diagram__ring" />
      <div className="loop-diagram__dot" />
      {STAGES.map((stage, i) => (
        <div
          key={stage}
          className="loop-diagram__stage machine"
          style={{
            top: `${STAGE_LAYOUT[i].top}%`,
            left: `${STAGE_LAYOUT[i].left}%`,
            animationDelay: `${STAGE_LAYOUT[i].delayS}s`,
          }}
        >
          {stage}
        </div>
      ))}
    </div>
  );
}
