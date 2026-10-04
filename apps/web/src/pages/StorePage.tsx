import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Logo } from "../App";
import { api, ApiError, formatInr, setToken, type Business, type Conversation, type Item, type User } from "../lib/api";
import { useSession } from "../session";

const UNIT: Record<string, string> = { kg: "kg", l: "litre", pc: "piece", pkt: "packet", g: "g", dozen: "dozen" };

export default function StorePage() {
  const { handle } = useParams();
  const { user, signIn } = useSession();
  const nav = useNavigate();
  const [data, setData] = useState<{ business: Business; items: Item[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<{ business: Business; items: Item[] }>(`/public/b/${handle}`).then(setData).catch(() => setError("This shop doesn't exist."));
  }, [handle]);

  async function startChat(e?: React.FormEvent) {
    e?.preventDefault();
    setBusy(true);
    try {
      if (!user) {
        const g = await api<{ token: string; user: User }>("/auth/guest", { body: { display_name: name.trim() || "Guest" } });
        setToken(g.token);
        signIn(g.token, g.user);
      }
      const c = await api<Conversation>(`/public/b/${handle}/chat`, { body: {} });
      nav(`/c/${c.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not open chat");
    } finally {
      setBusy(false);
    }
  }

  if (error) return <div className="placeholder"><Logo /><p>{error}</p><Link to="/">Go home</Link></div>;
  if (!data) return <div className="splash"><Logo /></div>;
  const b = data.business;

  return (
    <div className="store">
      <header className="store-head">
        <Logo small />
        {user ? <Link to="/" className="chip">My chats</Link> : <Link to="/login" className="chip">Sign in</Link>}
      </header>
      <section className="store-hero">
        <div className="avatar big business">{b.name.slice(0, 1)}</div>
        <div>
          <h1>{b.name}</h1>
          <p className="muted">{b.address}</p>
          <p className="small">{b.hours && <>🕒 {b.hours}</>} {b.delivery_note && <> · 🛵 {b.delivery_note}</>}</p>
        </div>
      </section>
      <section className="store-cta">
        <p>Order on chat in Hindi, Tamil, Telugu, Bengali, Marathi, English or Hinglish — pay with any UPI app.</p>
        {user ? (
          <button className="primary" disabled={busy} onClick={() => startChat()}>Chat to order</button>
        ) : (
          <form className="row" onSubmit={startChat}>
            <input placeholder="Your name" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} />
            <button className="primary" disabled={busy}>Chat to order — no sign-up</button>
          </form>
        )}
      </section>
      <section className="catalog">
        {data.items.map((i) => (
          <div key={i.id} className={`item ${i.stock === 0 ? "oos" : ""}`}>
            <div className="item-name">{i.name}</div>
            <div className="muted small">{i.aliases.slice(0, 3).join(" · ")}</div>
            <div className="price">{formatInr(i.price_paise)} <span className="muted small">/ {UNIT[i.unit] ?? i.unit}</span></div>
            {i.stock === 0 && <span className="badge warn">Out of stock</span>}
          </div>
        ))}
      </section>
    </div>
  );
}
