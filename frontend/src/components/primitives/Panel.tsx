/**
 * Panel — shared instrument chrome: hairline border, title bar with a status
 * dot slot, and a pulse glow driven by usePanelPulse(id) (fired from dispatch
 * via the theater registry whenever one of this panel's events lands).
 */

import type { ReactNode } from 'react';
import type { PanelId } from '../../types/domain';
import { usePanelPulse } from '../../theater/pulse';
import { StatusDot, type DotState } from './StatusDot';

export interface PanelProps {
  id: PanelId;
  title: string;
  status?: DotState | undefined;
  actions?: ReactNode | undefined;
  className?: string | undefined;
  children: ReactNode;
}

export function Panel({ id, title, status, actions, className, children }: PanelProps) {
  const pulsing = usePanelPulse(id);
  return (
    <section
      className={`panel${className ? ` ${className}` : ''}`}
      data-panel={id}
      data-pulse={pulsing || undefined}
    >
      <header className="panel__bar">
        {status ? <StatusDot state={status} /> : null}
        <h2 className="panel__title machine">{title}</h2>
        {actions ? <div className="panel__actions">{actions}</div> : null}
      </header>
      <div className="panel__body">{children}</div>
    </section>
  );
}
