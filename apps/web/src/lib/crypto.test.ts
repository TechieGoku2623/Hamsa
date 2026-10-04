import { describe, expect, it } from "vitest";
import { decryptFrom, encryptFor, exportPublic, generateIdentity, securityCode } from "./crypto";

async function device(id: string) {
  const keys = await generateIdentity();
  return { id, keys, public_key: await exportPublic(keys.publicKey) };
}

describe("E2EE v0", () => {
  it("encrypts once and every recipient device can decrypt; server sees no plaintext", async () => {
    const alice = await device("alice-phone");
    const bob = await device("bob-phone");
    const aliceWeb = await device("alice-web");
    const plain = { text: "कल 2 बजे मिलते हैं 👋", sent_at: "2026-10-04T10:00:00Z" };
    const envs = await encryptFor(alice.keys.privateKey, alice.id, [bob, aliceWeb], "conv1", "msg1", plain);
    expect(envs.map((e) => e.recipient_device_id)).toEqual(["bob-phone", "alice-web"]);
    expect(JSON.stringify(envs)).not.toContain("बजे");
    for (const [d, env] of [[bob, envs[0]], [aliceWeb, envs[1]]] as const) {
      const out = await decryptFrom(d.keys.privateKey, d.id, alice.id, alice.public_key, "conv1", "msg1", env.payload);
      expect(out).toEqual(plain);
    }
  });

  it("rejects tampering, wrong recipient and replay into another conversation", async () => {
    const alice = await device("a");
    const bob = await device("b");
    const eve = await device("e");
    const [env] = await encryptFor(alice.keys.privateKey, alice.id, [bob], "conv1", "msg1", { text: "pay ₹500", sent_at: "t" });
    const tampered = { ...env.payload, ct: env.payload.ct.slice(0, -2) + (env.payload.ct.endsWith("A") ? "BB" : "AA") };
    await expect(decryptFrom(bob.keys.privateKey, bob.id, alice.id, alice.public_key, "conv1", "msg1", tampered)).rejects.toThrow();
    await expect(decryptFrom(eve.keys.privateKey, eve.id, alice.id, alice.public_key, "conv1", "msg1", env.payload)).rejects.toThrow();
    await expect(decryptFrom(bob.keys.privateKey, bob.id, alice.id, alice.public_key, "conv2", "msg1", env.payload)).rejects.toThrow();
  });

  it("private keys are not extractable", async () => {
    const d = await device("x");
    await expect(crypto.subtle.exportKey("jwk", d.keys.privateKey)).rejects.toThrow();
  });

  it("security code is symmetric and changes when a key changes", async () => {
    const a = await device("a");
    const b = await device("b");
    const c = await device("c");
    const ab = await securityCode([a.public_key, b.public_key]);
    expect(ab).toBe(await securityCode([b.public_key, a.public_key]));
    expect(ab).not.toBe(await securityCode([a.public_key, c.public_key]));
    expect(ab.split(" ")).toHaveLength(12);
  });
});
