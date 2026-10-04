type Handler = (event: { type: string; [k: string]: unknown }) => void;

/** WebSocket with reconnect and heartbeat; listeners survive reconnects. */
export class Realtime {
  private ws: WebSocket | null = null;
  private handlers = new Set<Handler>();
  private stopped = false;
  private retry = 0;
  private heartbeat: ReturnType<typeof setInterval> | null = null;
  onOpen: (() => void) | null = null;

  constructor(private url: string) {}

  start() {
    this.stopped = false;
    this.connect();
  }

  stop() {
    this.stopped = true;
    if (this.heartbeat) clearInterval(this.heartbeat);
    this.ws?.close();
  }

  on(h: Handler): () => void {
    this.handlers.add(h);
    return () => this.handlers.delete(h);
  }

  send(event: object) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(event));
  }

  private connect() {
    const ws = new WebSocket(this.url);
    this.ws = ws;
    ws.onopen = () => {
      this.retry = 0;
      if (this.heartbeat) clearInterval(this.heartbeat);
      this.heartbeat = setInterval(() => this.send({ type: "ping" }), 25000);
      this.onOpen?.();
    };
    ws.onmessage = (e) => {
      const event = JSON.parse(e.data);
      for (const h of this.handlers) h(event);
    };
    ws.onclose = () => {
      if (this.heartbeat) clearInterval(this.heartbeat);
      if (this.stopped) return;
      const delay = Math.min(30000, 500 * 2 ** this.retry++);
      setTimeout(() => this.connect(), delay);
    };
  }
}
