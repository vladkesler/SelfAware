/**
 * StatusDot — instrument LED. idle: dim; live: signal-orange heartbeat; busy:
 * charge heartbeat (current flowing, verdict pending); alert: the reserved
 * red. Purely presentational.
 */

export type DotState = 'idle' | 'live' | 'busy' | 'alert';

export function StatusDot({ state }: { state: DotState }) {
  return <span className={`dot dot--${state}`} aria-hidden="true" />;
}
