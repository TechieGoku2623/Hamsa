import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Logo } from "../App";
import { api, ApiError, formatInr, type Business, type Conversation, type Item, type Order } from "../lib/api";
import { useSession } from "../session";
import { conversationTitle } from "./HomePage";

const STATUS_LABEL: Record<string, string> = {
  pending_payment: "Awaiting payment", payment_claimed: "Customer says paid", paid: "Paid", preparing: "Preparing",
  ready: "Ready", delivered: "Delivered", cancelled: "Cancelled",
};
const NEXT: Record<string, { status: string; label: string }[]> = {
  pending_payment: [{ status: "paid", label: "Mark paid" }, { status: "preparing", label: "Cash on delivery" }, { status: "cancelled", label: "Cancel" }],
  payment_claimed: [{ status: "paid", label: "Confirm payment received" }, { status: "cancelled", label: "Cancel" }],
  paid: [{ status: "preparing", label: "Start preparing" }, { status: "ready", label: "Ready" }, { status: "cancelled", label: "Cancel & refund" }],
  preparing: [{ status: "ready", label: "Ready" }, { status: "delivered", label: "Delivered" }],
  ready: [{ status: "delivered", label: "Delivered" }],
};
const UNITS = ["kg", "g", "l", "pc", "pkt", "dozen"];

function CreateBusiness({ onCreated }: { onCreated: (b: Business) => void }) {
  const [f, setF] = useState({ handle: "", name: "", category: "kirana", vpa: "", address: "", hours: "", delivery_note: "" });
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      onCreated(await api<Business>("/businesses", { body: f }));
    } catch (err) {
      setError(err instanceof ApiError ? (typeof err.detail === "string" ? err.detail : "Please check the fields") : "Failed");
    }
  }
  return (
    <form className="card stack narrow" onSubmit={submit}>
      <h2>Set up your business on Hamsa</h2>
      <p className="muted">Customers chat with your AI assistant in their own language and pay you directly by UPI.</p>
      <label>Business name<input value={f.name} onChange={set("name")} required placeholder="Sharma Kirana Store" /></label>
      <label>Link handle<div className="phone-input"><span>hamsa/b/</span><input value={f.handle} onChange={(e) => setF({ ...f, handle: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "") })} required placeholder="sharma-kirana" /></div></label>
      <label>Type
        <select value={f.category} onChange={set("category")}>
          {["kirana", "restaurant", "pharmacy", "salon", "clinic", "tuition", "boutique", "services"].map((c) => <option key={c}>{c}</option>)}
        </select>
      </label>
      <label>UPI ID (money comes straight to you)<input value={f.vpa} onChange={set("vpa")} placeholder="yourshop@okaxis" /></label>
      <label>Address<input value={f.address} onChange={set("address")} /></label>
      <label>Hours<input value={f.hours} onChange={set("hours")} placeholder="7am–10pm, all days" /></label>
      <label>Delivery note<input value={f.delivery_note} onChange={set("delivery_note")} placeholder="Free delivery within 2 km" /></label>
      {error && <p className="error">{error}</p>}
      <button className="primary">Create business</button>
    </form>
  );
}

function Inbox({ biz }: { biz: Business }) {
  const { user, rt } = useSession();
  const [convs, setConvs] = useState<Conversation[]>([]);
  const load = useCallback(() => api<Conversation[]>(`/businesses/${biz.id}/conversations`).then(setConvs), [biz.id]);
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => rt?.on((ev) => {
    if (["business_message", "needs_human", "conversation"].includes(ev.type)) load();
  }), [rt, load]);
  if (convs.length === 0) return <p className="muted">No customer chats yet. Share your link: <code>{location.origin}/b/{biz.handle}</code></p>;
  return (
    <ul className="table-list">
      {convs.map((c) => (
        <li key={c.id}>
          <Link to={`/c/${c.id}`} className="row between">
            <div>
              <b>{conversationTitle(c, user!.id)}</b>
              <div className="muted small ellipsis">{c.last_text}</div>
            </div>
            <div className="row">
              {c.needs_human && <span className="badge warn">Needs you</span>}
              <span className={`badge ${c.ai_enabled ? "ok" : ""}`}>{c.ai_enabled ? "AI on" : "AI off"}</span>
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function Orders({ biz }: { biz: Business }) {
  const { rt } = useSession();
  const [orders, setOrders] = useState<Order[]>([]);
  const load = useCallback(() => api<Order[]>(`/businesses/${biz.id}/orders`).then(setOrders), [biz.id]);
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => rt?.on((ev) => {
    if (ev.type === "order") load();
  }), [rt, load]);
  async function move(o: Order, status: string) {
    await api(`/orders/${o.id}`, { method: "PATCH", body: { status } });
    load();
  }
  const today = orders.filter((o) => new Date(o.created_at).toDateString() === new Date().toDateString() && o.status !== "cancelled");
  return (
    <>
      <div className="stats">
        <div><span className="muted small">Orders today</span><b>{today.length}</b></div>
        <div><span className="muted small">Sales today</span><b>{formatInr(today.reduce((s, o) => s + o.total_paise, 0))}</b></div>
        <div><span className="muted small">To confirm</span><b>{orders.filter((o) => o.status === "payment_claimed").length}</b></div>
      </div>
      {orders.length === 0 && <p className="muted">No orders yet.</p>}
      <ul className="table-list">
        {orders.map((o) => (
          <li key={o.id} className="order">
            <div className="row between">
              <div>
                <b>{o.code}</b> <span className={`badge status-${o.status}`}>{STATUS_LABEL[o.status]}</span>
                <div className="muted small">{new Date(o.created_at).toLocaleString("en-IN")}</div>
              </div>
              <b>{formatInr(o.total_paise)}</b>
            </div>
            <div className="small">{o.items.map((i) => `${i.qty} ${i.unit} ${i.name}`).join(" · ")}</div>
            <div className="row wrap">
              {(NEXT[o.status] ?? []).map((n) => <button key={n.status} className={n.status === "cancelled" ? "danger" : ""} onClick={() => move(o, n.status)}>{n.label}</button>)}
              <Link className="chip ghost" to={`/c/${o.conversation_id}`}>Open chat</Link>
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}

function Catalog({ biz }: { biz: Business }) {
  const [items, setItems] = useState<Item[]>([]);
  const [f, setF] = useState({ sku: "", name: "", aliases: "", price: "", unit: "pc", stock: "" });
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api<Item[]>(`/businesses/${biz.id}/items`).then(setItems), [biz.id]);
  useEffect(() => {
    load();
  }, [load]);
  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api(`/businesses/${biz.id}/items`, {
        body: {
          sku: f.sku || f.name.toUpperCase().replace(/[^A-Z0-9]+/g, "-").slice(0, 40),
          name: f.name, aliases: f.aliases.split(",").map((a) => a.trim()).filter(Boolean),
          price_paise: Math.round(parseFloat(f.price) * 100), unit: f.unit, stock: f.stock === "" ? null : parseInt(f.stock, 10),
        },
      });
      setF({ sku: "", name: "", aliases: "", price: "", unit: "pc", stock: "" });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? (typeof err.detail === "string" ? err.detail : "Check the fields") : "Failed");
    }
  }
  async function patch(i: Item, body: Partial<Item>) {
    await api(`/items/${i.id}`, { method: "PATCH", body });
    load();
  }
  return (
    <>
      <form className="card add-item" onSubmit={add}>
        <input placeholder="Item name (e.g. Sugar)" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required />
        <input placeholder="Other names, comma separated (चीनी, cheeni)" value={f.aliases} onChange={(e) => setF({ ...f, aliases: e.target.value })} />
        <input placeholder="Price ₹" inputMode="decimal" value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} required />
        <select value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })}>{UNITS.map((u) => <option key={u}>{u}</option>)}</select>
        <input placeholder="Stock (optional)" inputMode="numeric" value={f.stock} onChange={(e) => setF({ ...f, stock: e.target.value })} />
        <button className="primary">Add item</button>
        {error && <p className="error">{error}</p>}
      </form>
      <table className="items">
        <thead><tr><th>Item</th><th>Other names</th><th>Price</th><th>Stock</th><th /></tr></thead>
        <tbody>
          {items.map((i) => (
            <tr key={i.id} className={i.active ? "" : "inactive"}>
              <td><b>{i.name}</b><div className="muted tiny">{i.sku}</div></td>
              <td className="small">{i.aliases.join(", ")}</td>
              <td>
                <input className="mini" defaultValue={(i.price_paise / 100).toString()} onBlur={(e) => {
                  const p = Math.round(parseFloat(e.target.value) * 100);
                  if (p > 0 && p !== i.price_paise) patch(i, { price_paise: p });
                }} /> / {i.unit}
              </td>
              <td>
                <input className="mini" defaultValue={i.stock ?? ""} placeholder="∞" onBlur={(e) => {
                  const s = e.target.value === "" ? null : parseInt(e.target.value, 10);
                  if (s !== i.stock && (s === null || s >= 0)) patch(i, { stock: s });
                }} />
              </td>
              <td><button className="link" onClick={() => patch(i, { active: !i.active })}>{i.active ? "Hide" : "Show"}</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function Settings({ biz, onSaved }: { biz: Business; onSaved: (b: Business) => void }) {
  const [f, setF] = useState(biz);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const { name, vpa, address, hours, delivery_note, faq } = f;
      onSaved(await api<Business>(`/businesses/${biz.id}`, { method: "PATCH", body: { name, vpa, address, hours, delivery_note, faq: faq.filter((x) => x.q && x.a) } }));
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(err instanceof ApiError ? String(err.message) : "Failed");
    }
  }
  const link = `${location.origin}/b/${biz.handle}`;
  return (
    <form className="card stack narrow" onSubmit={save}>
      <label>Your shop link
        <div className="row"><input readOnly value={link} /><button type="button" onClick={() => navigator.clipboard?.writeText(link)}>Copy</button></div>
      </label>
      <label>Name<input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
      <label>UPI ID<input value={f.vpa} onChange={(e) => setF({ ...f, vpa: e.target.value })} /></label>
      <label>Address<input value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} /></label>
      <label>Hours<input value={f.hours} onChange={(e) => setF({ ...f, hours: e.target.value })} /></label>
      <label>Delivery note<input value={f.delivery_note} onChange={(e) => setF({ ...f, delivery_note: e.target.value })} /></label>
      <h3>Answers the AI can give (FAQ)</h3>
      {f.faq.map((q, i) => (
        <div key={i} className="faq-row">
          <input placeholder="Question" value={q.q} onChange={(e) => setF({ ...f, faq: f.faq.map((x, j) => (j === i ? { ...x, q: e.target.value } : x)) })} />
          <input placeholder="Answer" value={q.a} onChange={(e) => setF({ ...f, faq: f.faq.map((x, j) => (j === i ? { ...x, a: e.target.value } : x)) })} />
          <button type="button" className="link" onClick={() => setF({ ...f, faq: f.faq.filter((_, j) => j !== i) })}>Remove</button>
        </div>
      ))}
      <button type="button" onClick={() => setF({ ...f, faq: [...f.faq, { q: "", a: "" }] })}>Add question</button>
      {error && <p className="error">{error}</p>}
      <button className="primary">{saved ? "Saved ✓" : "Save"}</button>
    </form>
  );
}

export default function DashboardPage() {
  const [biz, setBiz] = useState<Business | null | undefined>(undefined);
  const [tab, setTab] = useState<"inbox" | "orders" | "catalog" | "settings">("orders");
  useEffect(() => {
    api<Business[]>("/businesses/mine").then((b) => setBiz(b[0] ?? null));
  }, []);
  return (
    <div className="dash">
      <header className="dash-head">
        <Link to="/"><Logo small /></Link>
        {biz && <div><b>{biz.name}</b> <span className="muted small">/b/{biz.handle}</span></div>}
        <Link to="/" className="chip">Chats</Link>
      </header>
      {biz === undefined ? null : biz === null ? (
        <CreateBusiness onCreated={setBiz} />
      ) : (
        <>
          <nav className="tabs">
            {(["orders", "inbox", "catalog", "settings"] as const).map((t) => (
              <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>{t[0].toUpperCase() + t.slice(1)}</button>
            ))}
          </nav>
          <div className="dash-body">
            {tab === "inbox" && <Inbox biz={biz} />}
            {tab === "orders" && <Orders biz={biz} />}
            {tab === "catalog" && <Catalog biz={biz} />}
            {tab === "settings" && <Settings biz={biz} onSaved={setBiz} />}
          </div>
        </>
      )}
    </div>
  );
}
