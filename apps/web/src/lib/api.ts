export interface User {
  id: string;
  display_name: string;
  phone: string | null;
  is_guest: boolean;
}

export interface Member {
  user_id: string;
  display_name: string;
  phone: string | null;
  role: string;
}

export interface Conversation {
  id: string;
  kind: "direct" | "group" | "business";
  title: string;
  members: Member[];
  business: { id: string; handle: string; name: string } | null;
  ai_enabled: boolean;
  needs_human: boolean;
  updated_at: string;
  last_text: string | null;
}

export interface DeviceInfo {
  id: string;
  user_id: string;
  name: string;
  public_key: JsonWebKey;
}

export interface Envelope {
  id: string;
  message_id: string;
  conversation_id: string;
  sender_user_id: string;
  sender_device_id: string;
  recipient_device_id: string;
  payload: Record<string, string | number>;
  created_at: string;
}

export interface UpiAction {
  type: "upi_pay";
  link: string;
  amount_paise: number;
  order_code: string;
}

export interface BusinessMessage {
  id: string;
  conversation_id: string;
  sender_type: "customer" | "agent" | "owner" | "system";
  sender_user_id: string | null;
  text: string;
  meta: { lang?: string; tier?: string; actions?: UpiAction[]; order_code?: string; status?: string };
  created_at: string;
}

export interface Business {
  id: string;
  handle: string;
  name: string;
  category: string;
  vpa: string;
  address: string;
  hours: string;
  delivery_note: string;
  faq: { q: string; a: string }[];
}

export interface Item {
  id: string;
  sku: string;
  name: string;
  aliases: string[];
  price_paise: number;
  unit: string;
  stock: number | null;
  active: boolean;
}

export interface Order {
  id: string;
  code: string;
  business_id: string;
  conversation_id: string;
  customer_user_id: string;
  items: { sku: string; name: string; qty: number; unit: string; price_paise: number }[];
  total_paise: number;
  status: string;
  upi_link: string;
  created_at: string;
  updated_at: string;
}

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "string" ? detail : `HTTP ${status}`);
  }
}

let token: string | null = null;

export function setToken(t: string | null) {
  token = t;
}

export async function api<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (init.body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`/api${path}`, {
    method: init.method ?? (init.body !== undefined ? "POST" : "GET"),
    headers,
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : null;
  if (!res.ok) throw new ApiError(res.status, data?.detail ?? res.statusText);
  return data as T;
}

export function formatInr(paise: number): string {
  const rupees = paise / 100;
  return "₹" + rupees.toLocaleString("en-IN", { minimumFractionDigits: paise % 100 ? 2 : 0, maximumFractionDigits: 2 });
}
