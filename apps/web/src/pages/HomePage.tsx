import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Logo } from "../App";
import BusinessChat from "../components/BusinessChat";
import NewChatDialog from "../components/NewChatDialog";
import PersonalChat from "../components/PersonalChat";
import { api, type Conversation } from "../lib/api";
import type { LocalMessage } from "../lib/store";
import { useSession } from "../session";

export function conversationTitle(c: Conversation, myId: string): string {
  if (c.kind === "group") return c.title;
  if (c.kind === "business") {
    const isOwner = c.members.some((m) => m.user_id === myId && m.role === "owner");
    return isOwner ? c.members.find((m) => m.role === "customer")?.display_name ?? "Customer" : c.business?.name ?? c.title;
  }
  return c.members.find((m) => m.user_id !== myId)?.display_name ?? "Chat";
}

function initials(s: string) {
  return s.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("") || "?";
}

export function Avatar({ name, kind }: { name: string; kind?: string }) {
  return <span className={`avatar ${kind ?? ""}`}>{initials(name)}</span>;
}

export default function HomePage() {
  const { user, rt, signOut } = useSession();
  const { id } = useParams();
  const nav = useNavigate();
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [dialog, setDialog] = useState<"direct" | "group" | null>(null);
  const [unread, setUnread] = useState<Record<string, number>>({});

  const refresh = useCallback(() => api<Conversation[]>("/conversations").then(setConvs).catch(() => undefined), []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!rt) return;
    return rt.on((ev) => {
      if (ev.type === "conversation" || ev.type === "business_message" || ev.type === "needs_human") refresh();
      if (ev.type === "business_message") {
        const m = ev.message as { conversation_id: string; sender_user_id: string | null };
        if (m.conversation_id !== id && m.sender_user_id !== user?.id) setUnread((u) => ({ ...u, [m.conversation_id]: (u[m.conversation_id] ?? 0) + 1 }));
      }
    });
  }, [rt, refresh, id, user?.id]);

  useEffect(() => {
    const onLocal = (e: Event) => {
      const m = (e as CustomEvent<LocalMessage>).detail;
      refresh();
      if (m.conversation_id !== id && m.sender_user_id !== user?.id) setUnread((u) => ({ ...u, [m.conversation_id]: (u[m.conversation_id] ?? 0) + 1 }));
    };
    window.addEventListener("hamsa:local-message", onLocal);
    return () => window.removeEventListener("hamsa:local-message", onLocal);
  }, [refresh, id, user?.id]);

  useEffect(() => {
    if (id) setUnread((u) => ({ ...u, [id]: 0 }));
  }, [id]);

  if (!user) return null;
  const active = convs.find((c) => c.id === id) ?? null;

  return (
    <div className={`app ${id ? "has-active" : ""}`}>
      <aside className="sidebar">
        <header className="side-head">
          <Logo small />
          <div className="side-actions">
            {!user.is_guest && <Link className="chip" to="/business">My business</Link>}
            <button className="chip ghost" onClick={signOut} title="Sign out">Sign out</button>
          </div>
        </header>
        <div className="me-row">
          <Avatar name={user.display_name} />
          <div>
            <b>{user.display_name}</b>
            <div className="muted small">{user.is_guest ? "Guest — verify your number to keep chats" : user.phone}</div>
          </div>
        </div>
        {user.is_guest ? (
          <Link className="banner" to={`/login?next=${encodeURIComponent(location.pathname)}`}>Verify your phone to save chats and message friends →</Link>
        ) : (
          <div className="new-row">
            <button className="primary" onClick={() => setDialog("direct")}>New chat</button>
            <button onClick={() => setDialog("group")}>New group</button>
          </div>
        )}
        <ul className="conv-list">
          {convs.length === 0 && <li className="empty muted">No chats yet. Start one, or open a shop link like <Link to="/b/sharma-kirana">/b/sharma-kirana</Link>.</li>}
          {convs.map((c) => {
            const title = conversationTitle(c, user.id);
            return (
              <li key={c.id}>
                <Link to={`/c/${c.id}`} className={`conv ${c.id === id ? "active" : ""}`}>
                  <Avatar name={title} kind={c.kind} />
                  <div className="conv-main">
                    <div className="conv-top">
                      <b>{title}</b>
                      {c.kind === "business" && <span className="badge biz">Business</span>}
                      {c.kind === "group" && <span className="badge">Group</span>}
                      {c.needs_human && c.members.some((m) => m.user_id === user.id && m.role === "owner") && <span className="badge warn">Needs you</span>}
                    </div>
                    <div className="muted small ellipsis">
                      {c.kind === "business" ? c.last_text ?? "Say hello" : "🔒 End-to-end encrypted"}
                    </div>
                  </div>
                  {(unread[c.id] ?? 0) > 0 && <span className="unread">{unread[c.id]}</span>}
                </Link>
              </li>
            );
          })}
        </ul>
      </aside>
      <main className="pane">
        {active ? (
          active.kind === "business" ? (
            <BusinessChat key={active.id} conv={active} onBack={() => nav("/")} onChanged={refresh} />
          ) : (
            <PersonalChat key={active.id} conv={active} onBack={() => nav("/")} />
          )
        ) : (
          <div className="placeholder">
            <Logo />
            <p>Pick a chat, or start a new one.</p>
            <p className="muted small">Personal and group chats are end-to-end encrypted. Messages are stored only on your devices.</p>
          </div>
        )}
      </main>
      {dialog && (
        <NewChatDialog
          mode={dialog}
          onClose={() => setDialog(null)}
          onCreated={(c) => {
            setDialog(null);
            refresh();
            nav(`/c/${c.id}`);
          }}
        />
      )}
    </div>
  );
}
