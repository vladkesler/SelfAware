/**
 * ScopeGrid — the machine at rest, alive on every channel. One live scope
 * tile per commissioned sensor (name · big reading · trace), in a responsive
 * grid: one fills the stage, two sit side by side, three–four tile 2×2.
 * Reuses ReadingScope; the tiles read their own rings independently.
 */

import type { DriverCard } from '../types/domain';
import { ReadingScope } from '../components/panels/ReadingScope';

export function ScopeGrid({ sensors }: { sensors: DriverCard[] }) {
  if (sensors.length === 0) {
    return <div className="scope__empty machine">no verified signal yet</div>;
  }
  return (
    <div className="scope-grid" data-count={Math.min(sensors.length, 4)}>
      {sensors.map((s) => (
        <div className="scope-grid__tile" key={s.slug}>
          <ReadingScope slug={s.slug} unit={s.unit} hero />
        </div>
      ))}
    </div>
  );
}
