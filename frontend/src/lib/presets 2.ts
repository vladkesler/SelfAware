/**
 * One-click commission presets — mirrors backend `Settings.default_specs()`
 * slugs (config.py, docs/hardware-bringup.md). These devices do NOT
 * self-announce on the bus — outputs have no I2C address or readback, and a
 * raw ADC pin can't reveal what's attached — so discovery never surfaces a
 * PresenceCard for them. The rail offers explicit launch buttons instead;
 * clicking one sends `cmd.commission { preset_slug }`.
 *
 * Keep this list in lockstep with config.py `default_specs()`.
 */
export interface CommissionPreset {
  slug: string;
  label: string;
  /** One-glance schema facts: `class · pins · unit` (mirrors default_specs()). */
  meta: string;
  /** True for user-taught schemas (localStorage), absent for built-ins. */
  custom?: boolean;
}

export const COMMISSION_PRESETS: CommissionPreset[] = [
  { slug: 'servo', label: 'Servo (SG90)', meta: 'output · i2c 0x22 · GP4/5' },
  { slug: 'buzzer', label: 'Buzzer', meta: 'output · pwm GP20' },
  { slug: 'fan', label: 'Fan (DC motor)', meta: 'output · i2c 0x22 · GP4/5' },
  { slug: 'ldr', label: 'Light (LDR)', meta: 'analog · GP27 · %' },
  { slug: 'pot', label: 'Potentiometer', meta: 'analog · GP26 · %' },
  { slug: 'shtc3', label: 'SHTC3 temp/hum', meta: 'digital_bus · i2c 0x70 · degC' },
  { slug: 'ultrasonic', label: 'Ultrasonic', meta: 'pulse_timing · GP14/15 · cm' },
];
