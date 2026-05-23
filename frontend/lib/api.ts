const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function token(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const t = token();
  const res = await fetch(`${BASE}/api/v1${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(t ? { Authorization: `Bearer ${t}` } : {}),
      ...(options.headers ?? {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }
  return res.json() as Promise<T>;
}

export const api = {
  register: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  login: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<User>("/auth/me"),

  brokerConnect: (body: BrokerConnectBody) =>
    request<BrokerStatus>("/broker/connect", { method: "POST", body: JSON.stringify(body) }),

  brokerDisconnect: () => request("/broker/disconnect", { method: "DELETE" }),

  brokerStatus: () => request<BrokerStatus>("/broker/status"),

  botStart: () => request("/bot/start", { method: "POST" }),
  botStop: () => request("/bot/stop", { method: "POST" }),
  botStatus: () => request<BotStatus>("/bot/status"),

  positions: () => request<Position[]>("/positions"),
  history: (params?: { symbol?: string; status?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.symbol) q.set("symbol", params.symbol);
    if (params?.status) q.set("status", params.status);
    if (params?.limit) q.set("limit", String(params.limit));
    return request<Trade[]>(`/history?${q}`);
  },
  account: () => request<AccountInfo>("/account"),

  getConfig: () => request<BotConfig>("/config"),
  updateConfig: (body: BotConfig) =>
    request<BotConfig>("/config", { method: "PUT", body: JSON.stringify(body) }),
};

// ── Types ─────────────────────────────────────────────────────────────────────
export interface User {
  id: number; email: string; broker_connected: boolean;
  mt5_login?: string; mt5_server?: string; created_at: string;
}
export interface BrokerConnectBody {
  mt5_login: string; mt5_password: string; mt5_server: string;
  account_type?: string; platform?: string;
}
export interface BrokerStatus {
  connected: boolean; mt5_login?: string; mt5_server?: string;
  balance?: number; equity?: number; currency?: string;
}
export interface BotStatus {
  running: boolean; started_at?: string; last_tick?: string;
  total_signals: number; trades_placed: number; recent_errors: string[];
}
export interface Position {
  id: string; symbol: string; direction: string; volume: number;
  open_price: number; current_price: number; profit: number;
  stop_loss?: number; take_profit?: number;
}
export interface Trade {
  id: number; order_id: string; symbol: string; direction: string;
  volume: number; open_price: number; close_price?: number;
  profit?: number; status: string; opened_at: string; closed_at?: string;
}
export interface AccountInfo {
  balance: number; equity: number; margin: number; free_margin: number; currency: string;
}
export interface BotConfig {
  symbol: string; timeframe: string; strategy_name: string;
  risk_percent: number; max_open_trades: number;
  atr_multiplier_sl: number; atr_multiplier_tp: number;
  ema_fast: number; ema_slow: number; rsi_period: number;
  rsi_overbought: number; rsi_oversold: number;
}
