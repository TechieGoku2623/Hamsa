import { useState } from "react";
import { api, ApiError, type Conversation, type User } from "../lib/api";

export default function NewChatDialog({ mode, onClose, onCreated }: {
  mode: "direct" | "group";
  onClose: () => void;
  onCreated: (c: Conversation) => void;
}) {
  const [phones, setPhones] = useState("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const list = phones.split(/[,\n]/).map((p) => p.trim()).filter(Boolean);
      const found = await api<User[]>("/contacts/lookup", { body: { phones: list } });
      if (found.length === 0) throw new Error("Nobody with that number is on Hamsa yet. Invite them!");
      const body = mode === "direct"
        ? { kind: "direct", peer_user_id: found[0].id }
        : { kind: "group", title, member_user_ids: found.map((u) => u.id) };
      onCreated(await api<Conversation>("/conversations", { body }));
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal stack" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h2>{mode === "direct" ? "New chat" : "New group"}</h2>
        {mode === "group" && (
          <label>
            Group name
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Family" required maxLength={120} />
          </label>
        )}
        <label>
          {mode === "direct" ? "Mobile number" : "Mobile numbers (comma or one per line)"}
          {mode === "direct" ? (
            <input autoFocus inputMode="tel" value={phones} onChange={(e) => setPhones(e.target.value)} placeholder="98765 43210" required />
          ) : (
            <textarea autoFocus rows={3} value={phones} onChange={(e) => setPhones(e.target.value)} placeholder={"98765 43210\n91234 56789"} required />
          )}
        </label>
        {error && <p className="error">{error}</p>}
        <div className="row end">
          <button type="button" onClick={onClose}>Cancel</button>
          <button className="primary" disabled={busy}>{busy ? "…" : mode === "direct" ? "Start chat" : "Create group"}</button>
        </div>
      </form>
    </div>
  );
}
