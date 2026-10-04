import { createStore, get, set, update } from "idb-keyval";

/** On-device history for end-to-end encrypted chats. The server never keeps it. */

export interface LocalMessage {
  id: string;
  conversation_id: string;
  sender_user_id: string;
  text: string;
  sent_at: string;
  status: "sending" | "sent" | "received" | "failed";
}

const db = typeof indexedDB !== "undefined" ? createStore("hamsa", "kv") : undefined;

export async function kvGet<T>(key: string): Promise<T | undefined> {
  return db ? get<T>(key, db) : undefined;
}

export async function kvSet(key: string, value: unknown): Promise<void> {
  if (db) await set(key, value, db);
}

export async function loadMessages(conversationId: string): Promise<LocalMessage[]> {
  return (await kvGet<LocalMessage[]>(`msgs:${conversationId}`)) ?? [];
}

export async function upsertMessage(m: LocalMessage): Promise<LocalMessage[]> {
  let result: LocalMessage[] = [];
  if (!db) return result;
  await update<LocalMessage[]>(
    `msgs:${m.conversation_id}`,
    (prev) => {
      const list = prev ? [...prev] : [];
      const i = list.findIndex((x) => x.id === m.id);
      if (i >= 0) list[i] = { ...list[i], ...m };
      else list.push(m);
      list.sort((a, b) => a.sent_at.localeCompare(b.sent_at));
      result = list;
      return list;
    },
    db,
  );
  return result;
}
