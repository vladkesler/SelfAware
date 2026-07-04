/** Client-generated command ids (correlate system.ack / system.error). */
export function newCommandId(): string {
  return crypto.randomUUID();
}
