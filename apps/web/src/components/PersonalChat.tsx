import { useEffect, useRef, useState } from "react";
import { type Conversation } from "../lib/api";
import { securityCode } from "../lib/crypto";
import { conversationDevices, sendPersonal } from "../lib/messenger";
import { loadMessages, type LocalMessage } from "../lib/store";
import { conversationTitle, Avatar } from "../pages/HomePage";
import { useSession } from "../session";
import Composer from "./Composer";

function time(iso: string) {
  return new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
}

export default function PersonalChat({ conv, onBack }: { conv: Conversation; onBack: () => void }) {
  const { user, identity, rt } = useSession();
  const [msgs, setMsgs] = useState<LocalMessage[]>([]);
  const [code, setCode] = useState<string | null>(null);
  const [typing, setTyping] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const title = conversationTitle(conv, user!.id);
  const names = Object.fromEntries(conv.members.map((m) => [m.user_id, m.display_name]));

  useEffect(() => {
    loadMessages(conv.id).then(setMsgs);
    const onLocal = (e: Event) => {
      const m = (e as CustomEvent<LocalMessage>).detail;
      if (m.conversation_id === conv.id) loadMessages(conv.id).then(setMsgs);
    };
    window.addEventListener("hamsa:local-message", onLocal);
    return () => window.removeEventListener("hamsa:local-message", onLocal);
  }, [conv.id]);

  useEffect(() => {
    if (!rt) return;
    let t: ReturnType<typeof setTimeout> | undefined;
    const off = rt.on((ev) => {
      if (ev.type === "typing" && ev.conversation_id === conv.id) {
        setTyping(conv.members.find((m) => m.user_id === ev.user_id)?.display_name ?? "Someone");
        clearTimeout(t);
        t = setTimeout(() => setTyping(null), 3000);
      }
    });
    return () => {
      off();
      clearTimeout(t);
    };
  }, [rt, conv]);

  useEffect(() => endRef.current?.scrollIntoView({ block: "end" }), [msgs.length]);

  async function send(text: string) {
    if (!identity) return;
    setMsgs(await sendPersonal(user!, identity, conv.id, text));
  }

  async function showCode() {
    if (code) return setCode(null);
    const devices = await conversationDevices(conv.id);
    setCode(await securityCode(devices.map((d) => d.public_key)));
  }

  return (
    <section className="chat">
      <header className="chat-head">
        <button className="back" onClick={onBack} aria-label="Back">‹</button>
        <Avatar name={title} kind={conv.kind} />
        <div className="grow">
          <b>{title}</b>
          <div className="muted small">
            {typing ? `${typing} is typing…` : conv.kind === "group" ? conv.members.map((m) => m.display_name).join(", ") : "🔒 End-to-end encrypted"}
          </div>
        </div>
        <button className="chip ghost" onClick={showCode}>{code ? "Hide" : "Security code"}</button>
      </header>
      {code && (
        <div className="notice">
          <b>Security code</b> — compare with the other person's screen. If it matches, nobody is in the middle.
          <code className="code">{code}</code>
        </div>
      )}
      <div className="messages">
        <div className="e2ee-note">🔒 Messages are end-to-end encrypted. Hamsa's servers only relay ciphertext and delete it once delivered.</div>
        {msgs.map((m) => {
          const mine = m.sender_user_id === user!.id;
          return (
            <div key={m.id} className={`bubble ${mine ? "mine" : "theirs"}`}>
              {!mine && conv.kind === "group" && <div className="sender">{names[m.sender_user_id] ?? "Member"}</div>}
              <div className="text">{m.text}</div>
              <div className="meta">
                {time(m.sent_at)}
                {mine && <span className={`tick ${m.status}`}>{m.status === "sending" ? "⏱" : m.status === "failed" ? "!" : "✓"}</span>}
              </div>
            </div>
          );
        })}
        <div ref={endRef} />
      </div>
      <Composer onSend={send} onTyping={() => rt?.send({ type: "typing", conversation_id: conv.id })} placeholder="Message" />
    </section>
  );
}
