/**
 * Hamsa E2EE v0: per-device P-256 ECDH identity keys + per-message AES-256-GCM content key,
 * wrapped separately for every recipient device with a key derived by HKDF-SHA-256.
 *
 * Gives confidentiality and integrity against the server; not forward secrecy or
 * post-compromise security. The production protocol is MLS (RFC 9420) via OpenMLS (memo §1A).
 */

const enc = new TextEncoder();
const dec = new TextDecoder();
const subtle = globalThis.crypto.subtle;

export const ALG = "P256-HKDF-AESGCM-v0";

export interface EnvelopePayload {
  [k: string]: string | number;
  v: number;
  alg: string;
  iv: string;
  ct: string;
  wiv: string;
  wk: string;
}

export interface Plain {
  text: string;
  sent_at: string;
}

export function b64(buf: ArrayBuffer | Uint8Array): string {
  const bytes = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function unb64(s: string): Uint8Array<ArrayBuffer> {
  const bin = atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4));
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export async function generateIdentity(): Promise<CryptoKeyPair> {
  // Private key is non-extractable: it can be stored in IndexedDB but never read back as bytes.
  return (await subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, false, ["deriveBits"])) as CryptoKeyPair;
}

export async function exportPublic(key: CryptoKey): Promise<JsonWebKey> {
  const jwk = await subtle.exportKey("jwk", key);
  return { kty: jwk.kty, crv: jwk.crv, x: jwk.x, y: jwk.y };
}

async function importPublic(jwk: JsonWebKey): Promise<CryptoKey> {
  return subtle.importKey("jwk", { kty: "EC", crv: "P-256", x: jwk.x, y: jwk.y }, { name: "ECDH", namedCurve: "P-256" }, false, []);
}

async function wrapKey(myPrivate: CryptoKey, theirPublic: JsonWebKey, messageId: string, from: string, to: string): Promise<CryptoKey> {
  const shared = await subtle.deriveBits({ name: "ECDH", public: await importPublic(theirPublic) }, myPrivate, 256);
  const hk = await subtle.importKey("raw", shared, "HKDF", false, ["deriveKey"]);
  return subtle.deriveKey(
    { name: "HKDF", hash: "SHA-256", salt: enc.encode(messageId), info: enc.encode(`hamsa|${ALG}|${from}|${to}`) },
    hk,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
}

function aad(conversationId: string, messageId: string, from: string): Uint8Array<ArrayBuffer> {
  return enc.encode(`${conversationId}|${messageId}|${from}`);
}

export async function encryptFor(
  myPrivate: CryptoKey,
  senderDeviceId: string,
  recipients: { id: string; public_key: JsonWebKey }[],
  conversationId: string,
  messageId: string,
  plain: Plain,
): Promise<{ recipient_device_id: string; payload: EnvelopePayload }[]> {
  const contentKeyRaw = crypto.getRandomValues(new Uint8Array(32));
  const contentKey = await subtle.importKey("raw", contentKeyRaw, "AES-GCM", false, ["encrypt"]);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await subtle.encrypt(
    { name: "AES-GCM", iv, additionalData: aad(conversationId, messageId, senderDeviceId) },
    contentKey,
    enc.encode(JSON.stringify(plain)),
  );
  return Promise.all(
    recipients.map(async (r) => {
      const kek = await wrapKey(myPrivate, r.public_key, messageId, senderDeviceId, r.id);
      const wiv = crypto.getRandomValues(new Uint8Array(12));
      const wk = await subtle.encrypt({ name: "AES-GCM", iv: wiv }, kek, contentKeyRaw);
      return {
        recipient_device_id: r.id,
        payload: { v: 0, alg: ALG, iv: b64(iv), ct: b64(ct), wiv: b64(wiv), wk: b64(wk) },
      };
    }),
  );
}

export async function decryptFrom(
  myPrivate: CryptoKey,
  myDeviceId: string,
  senderDeviceId: string,
  senderPublic: JsonWebKey,
  conversationId: string,
  messageId: string,
  payload: EnvelopePayload,
): Promise<Plain> {
  if (payload.alg !== ALG) throw new Error(`unsupported algorithm ${payload.alg}`);
  const kek = await wrapKey(myPrivate, senderPublic, messageId, senderDeviceId, myDeviceId);
  const raw = await subtle.decrypt({ name: "AES-GCM", iv: unb64(payload.wiv) }, kek, unb64(payload.wk));
  const contentKey = await subtle.importKey("raw", raw, "AES-GCM", false, ["decrypt"]);
  const pt = await subtle.decrypt(
    { name: "AES-GCM", iv: unb64(payload.iv), additionalData: aad(conversationId, messageId, senderDeviceId) },
    contentKey,
    unb64(payload.ct),
  );
  return JSON.parse(dec.decode(pt)) as Plain;
}

/** Human-comparable code for a set of device keys, like Signal/WhatsApp "safety numbers". */
export async function securityCode(keys: JsonWebKey[]): Promise<string> {
  const material = keys.map((k) => `${k.x}.${k.y}`).sort().join("|");
  const digest = new Uint8Array(await subtle.digest("SHA-256", enc.encode(material)));
  const groups: string[] = [];
  for (let i = 0; i < 12; i++) {
    const n = ((digest[i * 2] << 8) | digest[i * 2 + 1]) % 100000;
    groups.push(n.toString().padStart(5, "0"));
  }
  return groups.join(" ");
}
