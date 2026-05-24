"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import {
  api,
  dashboardWsUrl,
  type AccountInfo,
  type BotStatus,
  type BrokerStatus,
  type Position,
} from "@/lib/api";
import {
  loadBrokerStatus,
  loadDashboardSnapshot,
  saveBrokerStatus,
  saveDashboardSnapshot,
  type DashboardSnapshot,
} from "@/lib/streamCache";

type DashboardWsMessage =
  | { type: "snapshot"; account: AccountInfo; positions: Position[]; bot_status: BotStatus }
  | { type: "account"; account: AccountInfo }
  | { type: "positions"; positions: Position[] }
  | { type: "bot_status"; bot_status: BotStatus }
  | { type: "error"; message: string };

const WS_RETRY_MS = 30000;

interface DashboardStreamContextValue {
  account: AccountInfo | null;
  positions: Position[];
  botStatus: BotStatus | null;
  live: boolean;
  error: string;
  brokerConnected: boolean | null;
  brokerStatus: BrokerStatus | null;
  brokerLoading: boolean;
  setError: (msg: string) => void;
  setBrokerStatus: (status: BrokerStatus) => void;
  refreshBrokerStatus: (showLoading?: boolean) => Promise<void>;
  disconnect: () => void;
}

const DashboardStreamContext = createContext<DashboardStreamContextValue | null>(
  null
);

function applySnapshot(
  msg: DashboardWsMessage & { type: "snapshot" },
  setAccount: (a: AccountInfo) => void,
  setPositions: (p: Position[]) => void,
  setBotStatus: (b: BotStatus) => void
) {
  setAccount(msg.account);
  setPositions(msg.positions);
  setBotStatus(msg.bot_status);
  saveDashboardSnapshot({
    account: msg.account,
    positions: msg.positions,
    bot_status: msg.bot_status,
  });
}

export function DashboardStreamProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const wsRef = useRef<WebSocket | null>(null);
  const enabledRef = useRef(true);
  const [wsAttempt, setWsAttempt] = useState(0);

  const cached = typeof window !== "undefined" ? loadDashboardSnapshot() : null;
  const cachedBroker = typeof window !== "undefined" ? loadBrokerStatus() : null;
  const [account, setAccount] = useState<AccountInfo | null>(cached?.account ?? null);
  const [positions, setPositions] = useState<Position[]>(cached?.positions ?? []);
  const [botStatus, setBotStatus] = useState<BotStatus | null>(cached?.bot_status ?? null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState("");
  const [brokerStatus, setBrokerStatusState] = useState<BrokerStatus | null>(cachedBroker);
  const [brokerConnected, setBrokerConnected] = useState<boolean | null>(
    cachedBroker ? cachedBroker.connected : null
  );
  const [brokerLoading, setBrokerLoading] = useState(!cachedBroker);
  const initialBrokerCachedRef = useRef(!!cachedBroker);
  const latestRef = useRef({ account, positions, botStatus });

  useEffect(() => {
    latestRef.current = { account, positions, botStatus };
  }, [account, positions, botStatus]);

  const persistPartial = useCallback((patch: Partial<DashboardSnapshot>) => {
    const l = latestRef.current;
    const account = patch.account ?? l.account;
    const bot_status = patch.bot_status ?? l.botStatus;
    if (!account || !bot_status) return;
    saveDashboardSnapshot({
      account,
      positions: patch.positions ?? l.positions,
      bot_status,
    });
  }, []);

  const refreshHttp = useCallback(async () => {
    try {
      const [s, a, p] = await Promise.all([
        api.botStatus(),
        api.account(),
        api.positions(),
      ]);
      setBotStatus(s);
      setAccount(a);
      setPositions(p);
      saveDashboardSnapshot({ account: a, positions: p, bot_status: s });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Request failed";
      if (msg.includes("401") || msg.includes("authenticated")) {
        router.push("/login");
      }
    }
  }, [router]);

  const setBrokerStatus = useCallback((status: BrokerStatus) => {
    setBrokerStatusState(status);
    setBrokerConnected(status.connected);
    saveBrokerStatus(status);
  }, []);

  const refreshBrokerStatus = useCallback(
    async (showLoading = true) => {
      if (showLoading) setBrokerLoading(true);
      try {
        const broker = await api.brokerStatus();
        if (!enabledRef.current) return;
        setBrokerStatus(broker);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Request failed";
        if (msg.includes("401") || msg.includes("authenticated")) {
          router.push("/login");
        } else {
          setBrokerStatus({ connected: false });
        }
      } finally {
        setBrokerLoading(false);
      }
    },
    [router, setBrokerStatus]
  );

  const disconnect = useCallback(() => {
    enabledRef.current = false;
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setLive(false);
    setAccount(null);
    setPositions([]);
    setBotStatus(null);
    setBrokerStatusState(null);
    setBrokerConnected(null);
    setBrokerLoading(false);
  }, []);

  useEffect(() => {
    if (!localStorage.getItem("token")) return;

    enabledRef.current = true;
    refreshBrokerStatus(!initialBrokerCachedRef.current);

    return () => {
      enabledRef.current = false;
    };
  }, [refreshBrokerStatus]);

  useEffect(() => {
    if (brokerConnected !== true || !enabledRef.current) return;

    const url = dashboardWsUrl();
    if (!url) {
      router.push("/login");
      return;
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    const ws = new WebSocket(url);
    wsRef.current = ws;
    let errorFromServer = false;

    ws.onopen = () => setLive(true);

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as DashboardWsMessage;
        if (msg.type === "snapshot") {
          applySnapshot(msg, setAccount, setPositions, setBotStatus);
        } else if (msg.type === "account") {
          setAccount(msg.account);
          persistPartial({ account: msg.account });
        } else if (msg.type === "positions") {
          setPositions(msg.positions);
          persistPartial({ positions: msg.positions });
        } else if (msg.type === "bot_status") {
          setBotStatus(msg.bot_status);
          persistPartial({ bot_status: msg.bot_status });
        } else if (msg.type === "error") {
          errorFromServer = true;
          setError(msg.message);
          setLive(false);
          ws.close();
          refreshHttp();
        }
      } catch {
        /* ignore */
      }
    };

    ws.onerror = () => {
      setLive(false);
      if (!errorFromServer) {
        setError("Live stream failed — using HTTP fallback.");
        refreshHttp();
      }
    };

    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    ws.onclose = () => {
      setLive(false);
      if (wsRef.current === ws) wsRef.current = null;
      if (enabledRef.current) {
        retryTimer = setTimeout(() => setWsAttempt((n) => n + 1), WS_RETRY_MS);
      }
    };

    return () => {
      if (retryTimer) clearTimeout(retryTimer);
      ws.close();
      if (wsRef.current === ws) wsRef.current = null;
    };
  }, [brokerConnected, wsAttempt, router, refreshHttp, persistPartial]);

  return (
    <DashboardStreamContext.Provider
      value={{
        account,
        positions,
        botStatus,
        live,
        error,
        brokerConnected,
        brokerStatus,
        brokerLoading,
        setError,
        setBrokerStatus,
        refreshBrokerStatus,
        disconnect,
      }}
    >
      {children}
    </DashboardStreamContext.Provider>
  );
}

export function useDashboardStreamOptional(): DashboardStreamContextValue | null {
  return useContext(DashboardStreamContext);
}

export function useDashboardStream(): DashboardStreamContextValue {
  const ctx = useDashboardStreamOptional();
  if (!ctx) {
    throw new Error("useDashboardStream must be used within DashboardStreamProvider");
  }
  return ctx;
}
