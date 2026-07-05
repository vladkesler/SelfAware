/**
 * agents — the honest cast, made legible. Three REAL agents (AUTHOR writes,
 * MEDIC repairs from the board's verbatim traceback, PILOT operates the
 * admitted drivers as tools) plus two participants that are NOT agents: the
 * HOST (deterministic scan + gate + plausibility) and the BOARD (real silicon,
 * the un-fakeable arbiter). This module is the single source of "who is on
 * stage and what is the one-glance headline" — the hero band and the relay
 * both read `derivePhase()`, so they can never disagree.
 */

import type { ActiveCommission } from '../state/slices/commission';

export type AgentKey = 'author' | 'medic' | 'pilot' | 'host' | 'board';

export interface Persona {
  key: AgentKey;
  label: string;
  glyph: string;
  role: string;
  /** true = a real LLM agent; false = a deterministic HOST/BOARD participant. */
  agent: boolean;
}

export const PERSONAS: Record<AgentKey, Persona> = {
  author: { key: 'author', label: 'AUTHOR', glyph: '✎', role: 'writes the driver', agent: true },
  medic: { key: 'medic', label: 'MEDIC', glyph: '✚', role: 'reads the error, rewrites', agent: true },
  pilot: { key: 'pilot', label: 'PILOT', glyph: '◇', role: 'operates the instruments', agent: true },
  host: { key: 'host', label: 'HOST', glyph: '·', role: 'scans & verifies', agent: false },
  board: { key: 'board', label: 'BOARD', glyph: '▚', role: 'runs it — the arbiter', agent: false },
};

export type StationState = 'pending' | 'active' | 'passed' | 'failed';

export interface Station {
  id: string;
  kind: AgentKey;
  label: string;
}

/** The relay, left → right: the story a part travels to come alive. */
export const RELAY: Station[] = [
  { id: 'scan', kind: 'host', label: 'SCAN' },
  { id: 'author', kind: 'author', label: 'AUTHOR' },
  { id: 'board', kind: 'board', label: 'BOARD' },
  { id: 'medic', kind: 'medic', label: 'MEDIC' },
  { id: 'verify', kind: 'host', label: 'VERIFY' },
  { id: 'pilot', kind: 'pilot', label: 'PILOT' },
];

export type PhaseTone = 'idle' | 'charge' | 'live' | 'alert';

export interface Phase {
  headline: string;
  sub: string;
  tone: PhaseTone;
  activeStation: string | null;
  agentKey: AgentKey | null;
  stationState: Record<string, StationState>;
}

const ALL_PENDING = (): Record<string, StationState> => ({
  scan: 'pending',
  author: 'pending',
  board: 'pending',
  medic: 'pending',
  verify: 'pending',
  pilot: 'pending',
});

/** The one-glance truth: the hero headline + which relay node is lit. */
export function derivePhase(active: ActiveCommission | undefined, driverCount: number): Phase {
  const st = ALL_PENDING();

  // --- idle: no commission on the bench --------------------------------------
  if (!active) {
    if (driverCount > 0) {
      st.scan = st.author = st.board = st.medic = st.verify = 'passed';
      st.pilot = 'active';
      return {
        headline: 'LIVE // SYSTEMS NOMINAL',
        sub: `${driverCount} live tool${driverCount === 1 ? '' : 's'} — ask the pilot to read a sensor or drive an actuator`,
        tone: 'live',
        activeStation: 'pilot',
        agentKey: 'pilot',
        stationState: st,
      };
    }
    return {
      headline: 'AWAITING HARDWARE',
      sub: 'plug a part into the board — the host scans the bus and hands a spec to the author',
      tone: 'idle',
      activeStation: 'scan',
      agentKey: null,
      stationState: st,
    };
  }

  // A commission exists → we already scanned to get its spec.
  st.scan = 'passed';
  const name = active.displayName || active.slug;
  const hadRepair = active.trail.some((r) => r.stage === 'repair');
  const generatedOk = active.trail.some((r) => r.stage === 'generate' && r.status === 'passed');
  const testedOk = active.trail.some((r) => r.stage === 'test' && r.status === 'passed');
  if (generatedOk) st.author = 'passed';
  if (hadRepair) st.medic = st.medic === 'pending' ? 'passed' : st.medic;

  // --- terminal outcomes ------------------------------------------------------
  if (active.outcome === 'passed') {
    st.author = 'passed';
    st.board = 'passed';
    st.verify = 'passed';
    if (hadRepair) st.medic = 'passed';
    st.pilot = 'active';
    return {
      headline: 'LIVE // SIGNAL ACQUIRED',
      sub: `${name} admitted — read_${active.slug} is now a live PILOT tool`,
      tone: 'live',
      activeStation: 'pilot',
      agentKey: 'pilot',
      stationState: st,
    };
  }
  if (active.outcome === 'failed') {
    const failed = hadRepair ? 'medic' : 'author';
    st[testedOk ? 'verify' : failed] = 'failed';
    st.board = 'failed';
    return {
      headline: 'NOT ADMITTED',
      sub: active.failReason || 'the board never vouched for it',
      tone: 'alert',
      activeStation: hadRepair ? 'medic' : 'board',
      agentKey: 'board',
      stationState: st,
    };
  }

  // --- running: read the current beat ----------------------------------------
  const stage = active.stage;
  const status = active.stageStatus;

  switch (stage) {
    case 'generate':
      st.author = status === 'failed' ? 'failed' : 'active';
      return {
        headline: 'AUTHOR // WRITING THE DRIVER',
        sub: `composing a driver for ${name} from the spec…`,
        tone: 'charge',
        activeStation: 'author',
        agentKey: 'author',
        stationState: st,
      };
    case 'repair':
      st.medic = status === 'failed' ? 'failed' : 'active';
      return {
        headline: 'MEDIC // READING THE ERROR',
        sub: "feeding the board's verbatim traceback back in — rewriting the driver…",
        tone: 'charge',
        activeStation: 'medic',
        agentKey: 'medic',
        stationState: st,
      };
    case 'validate':
      st.author = status === 'failed' ? 'failed' : 'active';
      return {
        headline: status === 'failed' ? 'REJECTED // THE GATE CAUGHT IT' : 'AUTHOR // CODE UNDER REVIEW',
        sub:
          status === 'failed'
            ? 'the static safety gate refused the code — back to the author'
            : 'the host gate vets the code before it may touch a pin…',
        tone: status === 'failed' ? 'alert' : 'charge',
        activeStation: 'author',
        agentKey: 'host',
        stationState: st,
      };
    case 'deploy':
      st.board = 'active';
      return {
        headline: 'THE BOARD // LOADING THE DRIVER',
        sub: 'loading the driver onto the board over the raw REPL…',
        tone: 'charge',
        activeStation: 'board',
        agentKey: 'board',
        stationState: st,
      };
    case 'test':
      if (status === 'failed') {
        st.board = 'failed';
        return {
          headline: 'TRACEBACK // THE BOARD REJECTED IT',
          sub: 'the chip raised a verbatim error — it cannot be hallucinated. handing it to the medic…',
          tone: 'alert',
          activeStation: 'board',
          agentKey: 'board',
          stationState: st,
        };
      }
      if (status === 'passed') {
        st.board = 'passed';
        st.verify = 'active';
        return {
          headline: 'HOST // VERIFYING THE READING',
          sub: 'checking the value is physically plausible before admission…',
          tone: 'charge',
          activeStation: 'verify',
          agentKey: 'host',
          stationState: st,
        };
      }
      st.board = 'active';
      return {
        headline: 'THE BOARD // RUNNING IT',
        sub: 'the real board runs the driver — this is the arbiter…',
        tone: 'charge',
        activeStation: 'board',
        agentKey: 'board',
        stationState: st,
      };
    default:
      return {
        headline: `COMMISSIONING ${name.toUpperCase()}`,
        sub: 'bringing a dead part to life on the real board…',
        tone: 'charge',
        activeStation: 'author',
        agentKey: 'author',
        stationState: st,
      };
  }
}
