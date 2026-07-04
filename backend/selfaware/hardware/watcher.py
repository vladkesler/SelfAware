"""DiscoveryWatcher — the plug-in -> materialize demo beat. Build-day body.

Rides the poller cadence UNDER THE LOCK (it calls session.exec, never the raw
transport) so scans can never interleave with a commission or a tool call.
Emits discovery.device_found / discovery.device_lost from events.payloads.

Honesty floor, encoded in confidence levels:
  * i2c + KNOWN_I2C_DEVICES hit -> confidence "exact" + suggested_spec
    (one-click commission in the DeviceRail).
  * adc signature change        -> confidence "unknown" — "something on GP27,
    what is it?" — the HUMAN names it; a voltage cannot reveal the part.
"""

from selfaware.config import Settings
from selfaware.events.bus import EventBus
from selfaware.hardware.session import BoardSession


class DiscoveryWatcher:
    """Periodic I2C-scan diffing + ADC-pin signature classification.

    MockBoard scripts a fake hotplug (0x70 appears; GP27 goes floating ->
    driven) so this whole beat runs offline once the build-day body lands.
    """

    def __init__(self, session: BoardSession, bus: EventBus, settings: Settings) -> None:
        self._session = session
        self._bus = bus
        self._settings = settings
        self._known_addrs: set[int] = set()  # last I2C scan result, for diffing

    async def start(self) -> None:
        """Build-day job: spawn the watch task — every N poller ticks, run
        I2C_SCAN_SNIPPET via session.exec (LOCK-acquiring, never the raw
        transport), then _diff_i2c; occasionally ADC_SIGNATURE_SNIPPET on
        unclaimed ADC-capable pins, then _classify_adc."""
        raise NotImplementedError("build day: watch task riding the poller cadence under THE lock")

    async def stop(self) -> None:
        """Build-day job: cancel + reap the watch task (same discipline as the
        poller: the lock drains any in-flight exec before cancel lands)."""
        raise NotImplementedError("build day: cancel + reap watch task")

    def _diff_i2c(self, scanned: list[int]) -> None:
        """Build-day job: diff against self._known_addrs.

        New addr  -> KNOWN_I2C_DEVICES lookup -> publish device_found
                     {bus:'i2c', addr, identity?, confidence:'exact'|'unknown',
                      suggested_spec?}.
        Gone addr -> publish device_lost{bus:'i2c', addr}.
        """
        raise NotImplementedError("build day: scan-diff -> discovery.* events")

    def _classify_adc(self, pin: int, samples: list[int]) -> str:
        """Build-day job: classify a u16 sample burst -> 'floating' | 'driven' | 'railed'.

        Fingerprints (the wiring-diagnostics gold):
          floating: noisy mid-scale — wide spread around ~32k, nothing attached
                    (a plausible-LOOKING value, which is exactly why range
                    checks alone must never pass a sensor).
          railed:   flat near 0 or 65535 — digital/ground-ish pin of a module:
                    right part, wrong wire ('wrong-pin signature').
          driven:   idles near ~half supply with a stable, low-noise level that
                    MOVES under stimulus — a real analog source.
        floating->driven transition == 'something just got plugged into GPn'
        -> device_found{bus:'adc', pin, confidence:'unknown'}.
        """
        raise NotImplementedError("build day: floating|driven|railed fingerprint classifier")
