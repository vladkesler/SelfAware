/**
 * WS protocol types — hand-written mirror of backend/selfaware/events/
 * (types.py + envelope.py + payloads.py). Canonical doc: docs/event-protocol.md.
 * If you change one side, change all three.
 *
 * seq semantics: global per backend process, monotonic, GAPS ARE LEGAL
 * (drop-oldest per subscriber). system.hello restates full state, so
 * reconnect == rehydrate; never try to replay missed events.
 */

export const PROTOCOL_VERSION = 1;

export type Stage = 'generate' | 'validate' | 'deploy' | 'test' | 'repair';
export type StageStatus = 'started' | 'passed' | 'failed';
export type ProtocolClass = 'analog' | 'digital_bus' | 'pulse_timing' | 'output';
export type DriverStatus = 'commissioning' | 'active' | 'failed';

/** Server→client envelope, generic over the dot-namespaced type + payload. */
interface Env<T extends string, P> {
  v: 1;
  type: T;
  ts: string; // ISO-8601, server clock
  seq: number; // global monotonic; gaps legal — log, never fatal
  payload: P;
}

// --- shared wire models -------------------------------------------------------

export interface BoardStatusP {
  connected: boolean;
  port_id: string | null;
  mock: boolean;
  busy: boolean;
}

export interface DriverSummary {
  slug: string;
  display_name: string;
  protocol_class: ProtocolClass;
  status: DriverStatus;
  unit: string;
  last_reading: number | null;
}

// --- payloads (mirror payloads.py) ---------------------------------------------

export interface SystemHello {
  server_version: string;
  protocol_v: number;
  board: BoardStatusP;
  drivers: DriverSummary[];
}
export interface SystemAck {
  cmd_id: string;
}
export interface SystemError {
  code: string;
  message: string;
  cmd_id?: string | null;
  detail?: string | null;
}

export interface BoardConnected {
  port_id: string;
  mock: boolean;
}
export interface BoardDisconnected {
  reason: string;
}

export interface CommissionStarted {
  commission_id: string;
  slug: string;
  display_name: string;
  protocol_class: ProtocolClass;
  pins: Record<string, number>;
  max_attempts: number;
}
export interface CommissionStage {
  commission_id: string;
  attempt: number;
  stage: Stage;
  status: StageStatus;
  detail: string;
}
export interface CommissionTraceback {
  commission_id: string;
  attempt: number;
  stage: Stage;
  /** VERBATIM board stderr — render raw, never trim or re-wrap. */
  traceback: string;
}
export interface CommissionPassed {
  commission_id: string;
  slug: string;
  attempts_used: number;
  reading: number | null;
  unit: string;
}
export interface CommissionFailed {
  commission_id: string;
  slug: string;
  attempts_used: number;
  reason: string;
  last_traceback?: string | null;
}

export interface AgentThought {
  agent: string;
  text: string;
}
export interface AgentToolCall {
  agent: string;
  tool: string;
  args: Record<string, unknown>;
  tool_call_id: string;
}
export interface AgentToolResult {
  agent: string;
  tool: string;
  tool_call_id: string;
  ok: boolean;
  preview: string;
}
export interface AgentMessage {
  agent: string;
  delta: string;
  done: boolean;
  usage?: { input_tokens: number; output_tokens: number } | null;
}

export interface SensorReading {
  slug: string;
  value: number;
  unit: string;
  /** Host verdict, never the model's opinion. */
  plausible: boolean;
}
export interface ActuatorState {
  slug: string;
  level: number;
  ok: boolean;
}

export interface DeviceFound {
  bus: 'i2c' | 'adc';
  addr?: number | null;
  pin?: number | null;
  identity?: string | null;
  confidence: 'exact' | 'unknown';
  suggested_spec?: Record<string, unknown> | null;
}
export interface DeviceLost {
  bus: 'i2c' | 'adc';
  addr?: number | null;
  pin?: number | null;
}

export interface DriverRegistered {
  slug: string;
  display_name: string;
  protocol_class: ProtocolClass;
  pins: Record<string, number>;
  tool_names: string[];
  code_hash: string;
  unit: string;
}
export interface DriverUpdated {
  slug: string;
  code_hash: string;
  reason: 'repair' | 'recommission';
}

export type PanelId = 'stepper' | 'terminal' | 'scope' | 'rail' | 'chat' | 'board' | 'feed';
export interface UiPanelHint {
  hint: 'focus' | 'pulse';
  target: PanelId;
}

/** The discriminated union the entire frontend keys on. */
export type ServerEvent =
  | Env<'system.hello', SystemHello>
  | Env<'system.ack', SystemAck>
  | Env<'system.error', SystemError>
  | Env<'board.connected', BoardConnected>
  | Env<'board.disconnected', BoardDisconnected>
  | Env<'board.status', BoardStatusP>
  | Env<'commission.started', CommissionStarted>
  | Env<'commission.stage', CommissionStage>
  | Env<'commission.traceback', CommissionTraceback>
  | Env<'commission.passed', CommissionPassed>
  | Env<'commission.failed', CommissionFailed>
  | Env<'agent.thought', AgentThought>
  | Env<'agent.tool_call', AgentToolCall>
  | Env<'agent.tool_result', AgentToolResult>
  | Env<'agent.message', AgentMessage>
  | Env<'sensor.reading', SensorReading>
  | Env<'actuator.state', ActuatorState>
  | Env<'discovery.device_found', DeviceFound>
  | Env<'discovery.device_lost', DeviceLost>
  | Env<'driver.registered', DriverRegistered>
  | Env<'driver.updated', DriverUpdated>
  | Env<'ui.panel', UiPanelHint>;

export type EventType = ServerEvent['type'];
export type EventOf<T extends EventType> = Extract<ServerEvent, { type: T }>;

export const KNOWN_EVENT_TYPES: readonly EventType[] = [
  'system.hello',
  'system.ack',
  'system.error',
  'board.connected',
  'board.disconnected',
  'board.status',
  'commission.started',
  'commission.stage',
  'commission.traceback',
  'commission.passed',
  'commission.failed',
  'agent.thought',
  'agent.tool_call',
  'agent.tool_result',
  'agent.message',
  'sensor.reading',
  'actuator.state',
  'discovery.device_found',
  'discovery.device_lost',
  'driver.registered',
  'driver.updated',
  'ui.panel',
] as const;

/** Valid envelope, unrecognized type — routed to the raw feed, never dropped. */
export interface UnknownServerEvent {
  v: 1;
  type: string;
  ts: string;
  seq: number;
  payload: unknown;
  __unknown: true;
}
export type AnyEvent = ServerEvent | UnknownServerEvent;

export function isKnownEvent(ev: AnyEvent): ev is ServerEvent {
  return !('__unknown' in ev);
}

// --- client→server commands -----------------------------------------------------

interface Cmd<T extends string, P> {
  type: T;
  id: string; // uuid, client-generated; correlates system.ack / system.error
  payload: P;
}

export interface CommissionCmdPayload {
  preset_slug?: string;
  slug?: string;
  display_name?: string;
  protocol_class?: ProtocolClass;
  pins?: Record<string, number>;
  i2c_addr?: number;
  expected_min?: number;
  expected_max?: number;
  unit?: string;
  stimulus_hint?: string;
  verify_with_slug?: string;
  extra_context?: string;
}

export type ClientCommand =
  | Cmd<'cmd.commission', CommissionCmdPayload>
  | Cmd<'cmd.read', { slug: string }>
  | Cmd<'cmd.set', { slug: string; level: number }>
  | Cmd<'cmd.chat', { text: string }>
  | Cmd<'cmd.board_scan', Record<string, never>>
  | Cmd<'cmd.stimulate', { slug: string; delta: number }>; // mock-only
