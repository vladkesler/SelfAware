/**
 * Fixed-capacity ring buffer. Backing store never grows; `forEach` is
 * allocation-free so the ReadingScope canvas loop can walk samples at 60fps
 * without GC pressure.
 */
export class RingBuffer<T> {
  private buf: (T | undefined)[];
  private head = 0; // next write index
  private count = 0;

  constructor(readonly capacity: number) {
    if (capacity <= 0) throw new Error('RingBuffer capacity must be > 0');
    this.buf = new Array<T | undefined>(capacity);
  }

  push(item: T): void {
    this.buf[this.head] = item;
    this.head = (this.head + 1) % this.capacity;
    if (this.count < this.capacity) this.count++;
  }

  /** Oldest → newest. Allocates; prefer forEach in hot paths. */
  toArray(): T[] {
    const out: T[] = new Array(this.count);
    this.forEach((item, i) => {
      out[i] = item;
    });
    return out;
  }

  /** Oldest → newest, allocation-free. */
  forEach(fn: (item: T, i: number) => void): void {
    const start = (this.head - this.count + this.capacity) % this.capacity;
    for (let i = 0; i < this.count; i++) {
      fn(this.buf[(start + i) % this.capacity] as T, i);
    }
  }

  get length(): number {
    return this.count;
  }

  get last(): T | undefined {
    if (this.count === 0) return undefined;
    return this.buf[(this.head - 1 + this.capacity) % this.capacity];
  }

  clear(): void {
    this.buf = new Array<T | undefined>(this.capacity);
    this.head = 0;
    this.count = 0;
  }
}
