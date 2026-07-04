/**
 * Console — the agent theater. CSS grid: BoardStatus strip on top, DeviceRail
 * left, center stage (CommissionStepper over TracebackPane + ReadingScope,
 * ChatDock docked below), EventFeed right. Panels are prop-complete and fed
 * from selectors; commands go out through getTransport().send().
 */

import { useMemo } from 'react';
import type { ClientCommand, CommissionCmdPayload } from '../types/events';
import type { DriverCard, PresenceCard } from '../types/domain';
import { useTransport } from '../hooks/useTransport';
import { getTransport } from '../lib/transport';
import { newCommandId } from '../lib/ids';
import { useStore } from '../state/store';
import {
  buildTermLines,
  useBoard,
  useChat,
  useCommission,
  useConnection,
  useDrivers,
  useProtocolMismatch,
} from '../state/selectors';
import { Panel } from '../components/primitives/Panel';
import { BoardStatus } from '../components/panels/BoardStatus';
import { CommissionStepper } from '../components/panels/CommissionStepper';
import { TracebackPane } from '../components/panels/TracebackPane';
import { ReadingScope } from '../components/panels/ReadingScope';
import { DeviceRail } from '../components/panels/DeviceRail';
import { ChatDock } from '../components/panels/ChatDock';
import { EventFeed } from '../theater/EventFeed';

function send(cmd: ClientCommand): void {
  if (!getTransport().send(cmd)) {
    console.warn('[console] command dropped — transport not open:', cmd.type);
  }
}

export default function Console() {
  useTransport();

  const connection = useConnection();
  const board = useBoard();
  const commission = useCommission();
  const drivers = useDrivers();
  const chat = useChat();
  const protocolMismatch = useProtocolMismatch();

  const active = commission.active;
  const termLines = useMemo(() => buildTermLines(active), [active]);

  const driverCards = useMemo(
    () => drivers.order.map((slug) => drivers.bySlug[slug]).filter((d): d is DriverCard => !!d),
    [drivers],
  );
  const presenceCards = useMemo(() => Object.values(drivers.presences), [drivers]);

  const scopeSlug = drivers.order.length > 0 ? drivers.order[drivers.order.length - 1] : undefined;
  const scopeUnit = scopeSlug ? drivers.bySlug[scopeSlug]?.unit : undefined;

  const onRead = (slug: string) =>
    send({ type: 'cmd.read', id: newCommandId(), payload: { slug } });

  const onSet = (slug: string, level: number) =>
    send({ type: 'cmd.set', id: newCommandId(), payload: { slug, level } });

  const onCommission = (p: PresenceCard) => {
    const payload: CommissionCmdPayload = p.suggestedSpec
      ? (p.suggestedSpec as CommissionCmdPayload)
      : p.bus === 'adc' && p.pin !== undefined
        ? {
            slug: `gp${p.pin}_sensor`,
            display_name: `GP${p.pin} sensor`,
            protocol_class: 'analog',
            pins: { adc: p.pin },
          }
        : {};
    send({ type: 'cmd.commission', id: newCommandId(), payload });
  };

  const onSendChat = (text: string) => {
    useStore.setState((s) => ({
      chat: {
        ...s.chat,
        messages: [...s.chat.messages, { role: 'user', text, at: new Date().toISOString() }],
      },
    }));
    send({ type: 'cmd.chat', id: newCommandId(), payload: { text } });
  };

  return (
    <div className="console">
      <div className="console__status">
        <BoardStatus
          ws={connection.status}
          board={board}
          mock={connection.mock}
          protocolMismatch={protocolMismatch}
        />
      </div>

      <div className="console__rail">
        <Panel id="rail" title="devices" status={driverCards.length > 0 ? 'live' : 'idle'}>
          <DeviceRail
            drivers={driverCards}
            presences={presenceCards}
            onRead={onRead}
            onSet={onSet}
            onCommission={onCommission}
          />
        </Panel>
      </div>

      <div className="console__center">
        <Panel
          id="stepper"
          title="commission"
          status={
            active
              ? active.outcome === 'failed' || active.stageStatus === 'failed'
                ? 'alert'
                : 'live'
              : 'idle'
          }
        >
          <CommissionStepper
            slug={active?.slug}
            protocolClass={active?.protocolClass}
            attempt={active?.attempt ?? 0}
            maxAttempts={active?.maxAttempts ?? 0}
            trail={active?.trail ?? []}
            activeStage={active?.stage}
            activeStatus={active?.stageStatus}
            outcome={active?.outcome}
          />
        </Panel>

        <div className="console__stage">
          <Panel id="terminal" title="board stderr" status={active?.lastTraceback ? 'alert' : 'idle'}>
            <TracebackPane lines={termLines} live={!!active && !active.outcome} />
          </Panel>
          <Panel id="scope" title="readings" status={scopeSlug ? 'live' : 'idle'}>
            {scopeSlug ? (
              <ReadingScope slug={scopeSlug} unit={scopeUnit} />
            ) : (
              <div className="scope__empty machine">no registered sensor yet</div>
            )}
          </Panel>
        </div>

        <Panel id="chat" title="copilot" className="console__chat">
          <ChatDock
            messages={chat.messages}
            streaming={chat.streaming}
            disabled={connection.status !== 'open'}
            onSend={onSendChat}
          />
        </Panel>
      </div>

      <div className="console__feed">
        <Panel id="feed" title="event stream" status={connection.status === 'open' ? 'live' : 'idle'}>
          <EventFeed />
        </Panel>
      </div>
    </div>
  );
}
