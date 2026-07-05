/**
 * Console — the stage. A slim fascia on top; the HERO band (the giant phase
 * headline + the agent relay + the live SIGNAL card) as the single focal
 * region; then three calm work columns — DRIVER (the code), AGENT (the active
 * agent's mind + the tools it's calling), and SERIAL (the milestone strip).
 * One story at a time, told once. Commands go out via getTransport().send().
 */

import { useMemo, useState } from 'react';
import type { ClientCommand } from '../types/events';
import type { DriverCard } from '../types/domain';
import {
  loadCustomSpecs,
  removeCustomSpec,
  saveCustomSpec,
  specMeta,
  toCommissionPayload,
  type CustomSpec,
} from '../lib/customSpecs';
import { useTransport } from '../hooks/useTransport';
import { getTransport } from '../lib/transport';
import { newCommandId } from '../lib/ids';
import { useStore } from '../state/store';
import {
  useBoard,
  useChat,
  useCommission,
  useConnection,
  useDrivers,
  useProtocolMismatch,
} from '../state/selectors';
import { COMMISSION_PRESETS } from '../lib/presets';
import { Panel } from '../components/primitives/Panel';
import { BoardStatus } from '../components/panels/BoardStatus';
import { HeroBand } from '../theater/HeroBand';
import { AgentColumn } from '../theater/AgentColumn';
import { SourcePane } from '../theater/SourcePane';
import { SerialLog } from '../theater/SerialLog';

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
  const running = !!active && !active.outcome;

  const driverCards = useMemo(
    () => drivers.order.map((slug) => drivers.bySlug[slug]).filter((d): d is DriverCard => !!d),
    [drivers],
  );

  const boardLabel = board.mock || connection.mock ? 'MOCK' : (board.portId ?? 'board');

  // The taught-device shelf: user-authored schemas from localStorage, merged
  // into the commission menu. A custom slug commissions with its FULL inline
  // spec (resolve_spec builds the BringupSpec server-side); built-ins keep
  // sending {preset_slug}.
  const [customSpecs, setCustomSpecs] = useState<CustomSpec[]>(loadCustomSpecs);

  const presets = useMemo(
    () => [
      ...COMMISSION_PRESETS,
      ...customSpecs.map((c) => ({
        slug: c.slug,
        label: c.display_name,
        meta: specMeta(c),
        custom: true,
      })),
    ],
    [customSpecs],
  );

  const commissionSpec = (spec: CustomSpec) =>
    send({ type: 'cmd.commission', id: newCommandId(), payload: toCommissionPayload(spec) });

  const onCommissionPreset = (slug: string) => {
    const custom = customSpecs.find((c) => c.slug === slug);
    if (custom) commissionSpec(custom);
    else send({ type: 'cmd.commission', id: newCommandId(), payload: { preset_slug: slug } });
  };

  const onTeach = (spec: CustomSpec) => setCustomSpecs(saveCustomSpec(spec));
  const onTeachAndCommission = (spec: CustomSpec) => {
    setCustomSpecs(saveCustomSpec(spec));
    commissionSpec(spec);
  };
  const onRemoveCustom = (slug: string) => setCustomSpecs(removeCustomSpec(slug));

  const onSendChat = (text: string) => {
    useStore.setState((s) => ({
      chat: {
        ...s.chat,
        messages: [...s.chat.messages, { role: 'user', text, at: new Date().toISOString() }],
      },
    }));
    send({ type: 'cmd.chat', id: newCommandId(), payload: { text } });
  };

  const driverStatus = running ? 'busy' : active?.outcome === 'passed' ? 'live' : 'idle';
  const agentStatus = running ? 'busy' : driverCards.length > 0 ? 'live' : 'idle';

  return (
    <div className="console">
      <div className="console__fascia">
        <BoardStatus
          ws={connection.status}
          board={board}
          mock={connection.mock}
          protocolMismatch={protocolMismatch}
          model={connection.server?.model}
          senses={driverCards.length}
          busySlug={running ? active.slug : undefined}
          lastError={connection.lastError}
          presets={presets}
          customSpecs={customSpecs}
          busy={board.busy || running}
          onCommission={onCommissionPreset}
          onTeach={onTeach}
          onTeachAndCommission={onTeachAndCommission}
          onRemoveCustom={onRemoveCustom}
        />
      </div>

      <div className="console__hero">
        <HeroBand active={active} drivers={driverCards} boardLabel={boardLabel} />
      </div>

      <div className="console__work">
        <Panel id="terminal" title="driver" className="work__driver" status={driverStatus}>
          {active ? (
            <SourcePane active={active} />
          ) : (
            <div className="source-pane--empty machine">
              no driver on the bench — commission a part to watch one get written
            </div>
          )}
        </Panel>

        <Panel id="chat" title="agent" className="work__agent" status={agentStatus}>
          <AgentColumn
            active={active}
            pilot={{
              messages: chat.messages,
              streaming: chat.streaming,
              tools: chat.tools,
              toolNames: driverCards.flatMap((d) => d.toolNames),
              disabled: connection.status !== 'open',
              fixtureMode: connection.mock,
              onSend: onSendChat,
            }}
          />
        </Panel>

        <Panel
          id="feed"
          title="serial"
          className="work__serial"
          status={connection.status === 'open' ? 'live' : 'idle'}
        >
          <SerialLog />
        </Panel>
      </div>
    </div>
  );
}
