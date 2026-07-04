/**
 * StatusDot — instrument LED. idle: dim; live: phosphor with a heartbeat
 * animation; alert: the reserved red. Purely presentational.
 */

export type DotState = 'idle' | 'live' | 'alert';

export function StatusDot({ state }: { state: DotState }) {
  return <span className={`dot dot--${state}`} aria-hidden="true" />;
}
