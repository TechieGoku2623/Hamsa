import { useEffect, useRef, useState } from "react";
import QRCode from "qrcode";
import { api, formatInr, type BusinessMessage, type Conversation, type UpiAction } from "../lib/api";
import { Avatar, conversationTitle } from "../pages/HomePage";
import { useSession } from "../session";
import Composer from "./Composer";

const QUICK = ["Menu", "My cart", "Confirm order", "Payment done", "Order status", "Talk to owner"];

function time(iso: string) {
  return new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
}

function UpiCard({ action, businessName }: { action: UpiAction; businessName: string }) {
  const [qr, setQr] = useState<string | null>(null);
  useEffect(() => {
    QRCode.toDataURL(action.link, { margin: 1, width: 180 }).then(setQr).catch(() => setQr(null));
  }, [action.link]);
  return (
    <div className="upi-card">
      <div className="upi-top">
        <div>
          <div className="muted small">Pay {businessName}</div>
          <div className="amount">{formatInr(action.amount_paise)}</div>
          <div className="muted small">Order {action.order_code}</div>
        </div>
        {qr && <img src={qr} alt={`UPI QR for order ${action.order_code}`} width={96} height={96} />}
      </div>
      <a className="primary block" href={action.link}>Pay with any UPI app</a>
      <div className="muted tiny">Money goes directly to the shop's UPI ID. Hamsa never holds your money.</div>
    </div>
  );
}

export default function BusinessChat({ conv, onBack, onChanged }: { conv: Conversation; onBack: () => void; onChanged: () => void }) {
  const { user, rt } = useSession();
  const [msgs, setMsgs] = useState<BusinessMessage[]>([]);
  const [aiOn, setAiOn] = useState(conv.ai_enabled);
  const [waiting, setWaiting] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const isOwner = conv.members.some((m) => m.user_id === user!.id && m.role === "owner");
  const title = conversationTitle(conv, user!.id);
  const bizName = conv.business?.name ?? "Business";

  useEffect(() => {
    api<BusinessMessage[]>(`/conversations/${conv.id}/messages`).then(setMsgs);
  }, [conv.id]);

  useEffect(() => setAiOn(conv.ai_enabled), [conv.ai_enabled]);

  useEffect(() => {
    if (!rt) return;
    return rt.on((ev) => {
      if (ev.type !== "business_message") return;
      const m = ev.message as BusinessMessage;
      if (m.conversation_id !== conv.id) return;
      if (m.sender_type === "agent") setWaiting(false);
      setMsgs((prev) => (prev.some((x) => x.id === m.id) ? prev : [...prev, m]));
    });
  }, [rt, conv.id]);

  useEffect(() => endRef.current?.scrollIntoView({ block: "end" }), [msgs.length, waiting]);

  async function send(text: string) {
    if (!isOwner && aiOn) setWaiting(true);
    try {
      const r = await api<{ message: BusinessMessage; reply: BusinessMessage | null }>(`/conversations/${conv.id}/messages`, { body: { text } });
      setMsgs((prev) => {
        const next = [...prev];
        for (const m of [r.message, r.reply]) if (m && !next.some((x) => x.id === m.id)) next.push(m);
        return next;
      });
      if (r.reply === null && !isOwner) {
        const c = await api<Conversation>(`/conversations/${conv.id}`);
        setAiOn(c.ai_enabled);
      }
    } finally {
      setWaiting(false);
    }
  }

  async function toggleAi() {
    const c = await api<Conversation>(`/conversations/${conv.id}/ai`, { body: { enabled: !aiOn } });
    setAiOn(c.ai_enabled);
    onChanged();
  }

  return (
    <section className="chat business">
      <header className="chat-head">
        <button className="back" onClick={onBack} aria-label="Back">‹</button>
        <Avatar name={title} kind="business" />
        <div className="grow">
          <b>{title}</b>
          <div className="muted small">{isOwner ? `Customer of ${bizName}` : `@${conv.business?.handle}`}</div>
        </div>
        {isOwner && (
          <button className={`toggle ${aiOn ? "on" : ""}`} onClick={toggleAi} title="When off, only you reply">
            <span className="dot" /> AI replies {aiOn ? "on" : "off"}
          </button>
        )}
      </header>
      <div className="notice ai">
        {isOwner
          ? "You're replying as the business. Turn AI replies off to take over the chat."
          : `${bizName} uses Hamsa AI to reply. Messages in this chat are processed by Hamsa on the business's behalf; personal chats stay end-to-end encrypted.`}
      </div>
      <div className="messages">
        {msgs.map((m) => {
          const mine = isOwner ? m.sender_type === "owner" || m.sender_type === "agent" : m.sender_type === "customer";
          if (m.sender_type === "system") return <div key={m.id} className="system-msg">{m.text}</div>;
          const actions = (m.meta.actions ?? []).filter((a) => a.type === "upi_pay");
          return (
            <div key={m.id} className={`bubble ${mine ? "mine" : "theirs"} ${m.sender_type}`}>
              {m.sender_type === "agent" && <div className="sender">{isOwner ? "Hamsa AI (for you)" : `${bizName} · AI`}</div>}
              {m.sender_type === "owner" && !isOwner && <div className="sender">{bizName} · Owner</div>}
              <div className="text">{m.text}</div>
              {actions.map((a) => (isOwner ? <div key={a.order_code} className="muted small">UPI request sent: {formatInr(a.amount_paise)} ({a.order_code})</div>
                : <UpiCard key={a.order_code} action={a} businessName={bizName} />))}
              <div className="meta">{time(m.created_at)}{isOwner && m.meta.tier ? ` · ${m.meta.tier}` : ""}</div>
            </div>
          );
        })}
        {waiting && <div className="bubble theirs typing-dots"><span /><span /><span /></div>}
        {!isOwner && !aiOn && <div className="system-msg">The owner will reply here personally.</div>}
        <div ref={endRef} />
      </div>
      {!isOwner && (
        <div className="quick">
          {QUICK.map((q) => <button key={q} className="chip" onClick={() => send(q)}>{q}</button>)}
        </div>
      )}
      <Composer onSend={send} placeholder={isOwner ? "Reply as the owner" : "Type in any language — e.g. 2 kg cheeni bhejo"} />
    </section>
  );
}
