import { api, ApiError, type DeviceInfo, type Envelope } from "./api";
import { decryptFrom, encryptFor, exportPublic, generateIdentity, type EnvelopePayload } from "./crypto";
import { kvGet, kvSet, upsertMessage, type LocalMessage } from "./store";

export interface Identity {
  deviceId: string;
  keys: CryptoKeyPair;
}

/** Load this browser's device identity for the user, registering a new device on first use. */
export async function ensureIdentity(userId: string): Promise<Identity> {
  const saved = await kvGet<Identity>(`identity:${userId}`);
  if (saved) {
    const mine = await api<DeviceInfo[]>("/devices");
    if (mine.some((d) => d.id === saved.deviceId)) return saved;
  }
  const keys = await generateIdentity();
  const dev = await api<DeviceInfo>("/devices", {
    body: { name: navigator.userAgent.includes("Mobile") ? "Mobile browser" : "Web browser", public_key: await exportPublic(keys.publicKey) },
  });
  const identity = { deviceId: dev.id, keys };
  await kvSet(`identity:${userId}`, identity);
  return identity;
}

const deviceCache = new Map<string, DeviceInfo[]>();

export function invalidateDevices() {
  deviceCache.clear();
}

async function devicesFor(conversationId: string, refresh = false): Promise<DeviceInfo[]> {
  if (!refresh && deviceCache.has(conversationId)) return deviceCache.get(conversationId)!;
  const list = await api<DeviceInfo[]>(`/conversations/${conversationId}/devices`);
  deviceCache.set(conversationId, list);
  return list;
}

export async function conversationDevices(conversationId: string): Promise<DeviceInfo[]> {
  return devicesFor(conversationId, true);
}

export async function sendPersonal(me: { id: string }, identity: Identity, conversationId: string, text: string): Promise<LocalMessage[]> {
  const messageId = crypto.randomUUID();
  const local: LocalMessage = {
    id: messageId, conversation_id: conversationId, sender_user_id: me.id, text, sent_at: new Date().toISOString(), status: "sending",
  };
  let list = await upsertMessage(local);
  for (let attempt = 0; attempt < 3; attempt++) {
    const recipients = (await devicesFor(conversationId, attempt > 0)).filter((d) => d.id !== identity.deviceId);
    if (recipients.length === 0) {
      list = await upsertMessage({ ...local, status: "sent" });
      return list;
    }
    const envelopes = await encryptFor(identity.keys.privateKey, identity.deviceId, recipients, conversationId, messageId, {
      text, sent_at: local.sent_at,
    });
    try {
      await api(`/conversations/${conversationId}/envelopes`, {
        body: { message_id: messageId, sender_device_id: identity.deviceId, envelopes },
      });
      return upsertMessage({ ...local, status: "sent" });
    } catch (e) {
      // 409 = someone added or removed a device; re-fetch and re-encrypt for the exact current set.
      if (!(e instanceof ApiError && e.status === 409)) break;
    }
  }
  return upsertMessage({ ...local, status: "failed" });
}

export async function receiveEnvelope(identity: Identity, env: Envelope): Promise<LocalMessage | null> {
  let devices = await devicesFor(env.conversation_id);
  let sender = devices.find((d) => d.id === env.sender_device_id);
  if (!sender) {
    devices = await devicesFor(env.conversation_id, true);
    sender = devices.find((d) => d.id === env.sender_device_id);
  }
  if (!sender) return null;
  try {
    const plain = await decryptFrom(identity.keys.privateKey, identity.deviceId, sender.id, sender.public_key, env.conversation_id,
      env.message_id, env.payload as EnvelopePayload);
    const msg: LocalMessage = {
      id: env.message_id, conversation_id: env.conversation_id, sender_user_id: env.sender_user_id, text: plain.text,
      sent_at: plain.sent_at, status: "received",
    };
    await upsertMessage(msg);
    return msg;
  } catch {
    return null;
  } finally {
    await api("/envelopes/ack", { body: { device_id: identity.deviceId, ids: [env.id] } }).catch(() => undefined);
  }
}

/** Pull envelopes queued while offline. */
export async function syncPending(identity: Identity): Promise<LocalMessage[]> {
  const pending = await api<Envelope[]>(`/devices/${identity.deviceId}/envelopes`);
  const out: LocalMessage[] = [];
  for (const env of pending) {
    const m = await receiveEnvelope(identity, env);
    if (m) out.push(m);
  }
  return out;
}
