import type { AccountInfo, BotStatus, BrokerStatus, Candle, Position } from "@/lib/api";

const DASHBOARD_KEY = "tb:dashboard";
const BROKER_KEY = "tb:broker";
const CHART_LAST_KEY = "tb:chart:last";

export interface DashboardSnapshot {
  account: AccountInfo;
  positions: Position[];
  bot_status: BotStatus;
}

export interface ChartCacheState {
  symbol: string;
  timeframe: string;
  candles: Candle[];
}

function chartKey(symbol: string, timeframe: string): string {
  return `tb:chart:${symbol}:${timeframe}`;
}

export function saveDashboardSnapshot(data: DashboardSnapshot): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.setItem(DASHBOARD_KEY, JSON.stringify(data));
  } catch {
    /* quota */
  }
}

export function saveBrokerStatus(status: BrokerStatus): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.setItem(BROKER_KEY, JSON.stringify(status));
  } catch {
    /* quota */
  }
}

export function loadBrokerStatus(): BrokerStatus | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(BROKER_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as BrokerStatus;
  } catch {
    return null;
  }
}

export function loadDashboardSnapshot(): DashboardSnapshot | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(DASHBOARD_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as DashboardSnapshot;
  } catch {
    return null;
  }
}

export function saveChartState(symbol: string, timeframe: string, candles: Candle[]): void {
  if (typeof window === "undefined") return;
  try {
    const state: ChartCacheState = { symbol, timeframe, candles };
    sessionStorage.setItem(chartKey(symbol, timeframe), JSON.stringify(candles));
    sessionStorage.setItem(CHART_LAST_KEY, JSON.stringify(state));
  } catch {
    /* quota */
  }
}

export function loadChartState(): ChartCacheState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(CHART_LAST_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as ChartCacheState;
  } catch {
    return null;
  }
}

export function loadChartCandles(symbol: string, timeframe: string): Candle[] | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(chartKey(symbol, timeframe));
    if (!raw) return null;
    return JSON.parse(raw) as Candle[];
  } catch {
    return null;
  }
}

export function clearStreamCache(): void {
  if (typeof window === "undefined") return;
  const keys: string[] = [];
  for (let i = 0; i < sessionStorage.length; i++) {
    const k = sessionStorage.key(i);
    if (k?.startsWith("tb:")) keys.push(k);
  }
  keys.forEach((k) => sessionStorage.removeItem(k));
}
