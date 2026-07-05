# Protocol class: analog (one ADC read)

- RP2040 ADC exists on GPIO 26, 27, 28 ONLY. `machine.ADC(n)` with the GPIO
  number from the spec; any other pin raises `ValueError` on the board.
- Read with `.read_u16()` — returns 0..65535. That is the WHOLE analog API on
  this chip. There is no `.atten()`, no `.width()`, no resolution knob; those
  are ESP32 calls and they crash here.
- Average a handful of samples in a `for _ in range(8):` loop with
  `time.sleep_ms(1)` between them — analog lines are noisy.
- Return a number in the spec's unit. If the unit is `raw` (or blank), return
  the raw u16 average unscaled. If the unit is `%`, normalize to 0..100 —
  `round(raw * 100 / 65535, 1)`; for any other unit, convert as the spec's
  context describes. The host judges plausibility in whatever unit the spec
  names, so match it.
- A reading parked at the bottom (~0) or top of the spec's window means the
  wrong pin or a floating line — if a previous attempt railed, re-check the
  pin number against the spec before touching anything else.
