"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  createChart,
  CandlestickSeries,
  ColorType,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import Navbar from "@/components/Navbar";
import { api, marketCandlesWsUrl, type Candle } from "@/lib/api";
import {
  loadChartCandles,
  loadChartState,
  saveChartState,
} from "@/lib/streamCache";

const FALLBACK_SYMBOLS = [
  "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
  "EURGBP", "EURJPY", "EURCHF", "EURAUD", "EURCAD", "EURNZD",
  "GBPJPY", "GBPCHF", "GBPAUD", "GBPCAD", "GBPNZD",
  "AUDJPY", "AUDNZD", "AUDCAD", "CADJPY", "CHFJPY", "NZDJPY", "NZDCAD",
  "XAUUSD", "XAGUSD",
];
const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"] as const;
const CHART_HTTP_POLL_MS = 5000;

function toBar(c: Candle) {
  return {
    time: c.time as UTCTimestamp,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  };
}

type WsMessage =
  | { type: "snapshot"; candles: Candle[] }
  | { type: "update"; candle: Candle }
  | { type: "error"; message: string };

export default function ChartsPage() {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const hydratedRef = useRef(false);

  const [symbol, setSymbol] = useState("XAUUSD");
  const [symbols, setSymbols] = useState<string[]>(FALLBACK_SYMBOLS);
  const [symbolFilter, setSymbolFilter] = useState("");
  const [symbolsLoading, setSymbolsLoading] = useState(false);
  const [timeframe, setTimeframe] = useState<string>("1m");
  const [loading, setLoading] = useState(false);
  const [live, setLive] = useState(false);
  const [error, setError] = useState("");
  const [brokerConnected, setBrokerConnected] = useState<boolean | null>(null);

  const filteredSymbols = symbols.filter((s) =>
    s.includes(symbolFilter.trim().toUpperCase())
  );

  const applyCandles = useCallback((candles: Candle[], fit = true) => {
    const series = seriesRef.current;
    if (!series || candles.length === 0) return;
    series.setData(candles.map(toBar));
    if (fit) chartRef.current?.timeScale().fitContent();
  }, []);

  const loadCandlesHttp = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    if (!silent) setError("");
    try {
      const data = await api.candles(symbol, timeframe);
      applyCandles(data);
      saveChartState(symbol, timeframe, data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load candles";
      if (msg.includes("401") || msg.includes("authenticated")) {
        router.push("/login");
        return;
      }
      if (msg.includes("broker")) setBrokerConnected(false);
      setError(msg);
    } finally {
      if (!silent) setLoading(false);
    }
  }, [symbol, timeframe, router, applyCandles]);

  useEffect(() => {
    if (!localStorage.getItem("token")) {
      router.push("/login");
      return;
    }

    (async () => {
      try {
        const status = await api.brokerStatus();
        setBrokerConnected(status.connected);
        if (!status.connected) {
          setError("Connect your MT5 broker to view charts.");
          return;
        }
        setSymbolsLoading(true);
        try {
          const { symbols: brokerSymbols } = await api.symbols();
          if (brokerSymbols.length > 0) {
            setSymbols(brokerSymbols);
            const cached = loadChartState();
            if (cached && brokerSymbols.includes(cached.symbol)) {
              setSymbol(cached.symbol);
              setTimeframe(cached.timeframe);
            } else {
              setSymbol((current) =>
                brokerSymbols.includes(current)
                  ? current
                  : brokerSymbols.includes("XAUUSD")
                    ? "XAUUSD"
                    : brokerSymbols[0]
              );
            }
          }
        } catch {
          setSymbols(FALLBACK_SYMBOLS);
        } finally {
          setSymbolsLoading(false);
        }
      } catch {
        setBrokerConnected(false);
        setError("Could not verify broker status.");
      }
    })();
  }, [router]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const chart = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: "#030712" },
        textColor: "#9ca3af",
      },
      grid: {
        vertLines: { color: "#1f2937" },
        horzLines: { color: "#1f2937" },
      },
      width: el.clientWidth,
      height: 480,
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });

    chartRef.current = chart;
    seriesRef.current = series;

    const cached =
      loadChartCandles(symbol, timeframe) ?? loadChartState()?.candles;
    if (cached && cached.length > 0) {
      applyCandles(cached);
      hydratedRef.current = true;
    }

    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth });
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      hydratedRef.current = false;
    };
  }, [applyCandles, symbol, timeframe]);

  useEffect(() => {
    if (brokerConnected !== true) return;
    if (!hydratedRef.current) {
      loadCandlesHttp();
    }
  }, [brokerConnected, symbol, timeframe, loadCandlesHttp]);

  useEffect(() => {
    if (brokerConnected !== true) return;

    const debounce = setTimeout(() => {
      const url = marketCandlesWsUrl(symbol, timeframe);
      if (!url) {
        router.push("/login");
        return;
      }

      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }

      setError("");
      setLive(false);
      if (!hydratedRef.current) setLoading(true);

      const ws = new WebSocket(url);
      wsRef.current = ws;
      let errorFromServer = false;

      ws.onopen = () => {
        setLive(true);
        setError("");
      };

      ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as WsMessage;
        const series = seriesRef.current;
        if (!series) return;

        if (msg.type === "snapshot") {
          applyCandles(msg.candles);
          saveChartState(symbol, timeframe, msg.candles);
          hydratedRef.current = true;
          setLoading(false);
        } else if (msg.type === "update") {
          series.update(toBar(msg.candle));
          const cached = loadChartCandles(symbol, timeframe) ?? [];
          const merged = [...cached];
          const idx = merged.findIndex((c) => c.time === msg.candle.time);
          if (idx >= 0) merged[idx] = msg.candle;
          else merged.push(msg.candle);
          merged.sort((a, b) => a.time - b.time);
          saveChartState(symbol, timeframe, merged);
          setLoading(false);
        } else if (msg.type === "error") {
          errorFromServer = true;
          setError(msg.message);
          setLive(false);
          setLoading(false);
          ws.close();
          loadCandlesHttp();
        }
      } catch {
        setLoading(false);
      }
    };

    ws.onerror = () => {
      setLive(false);
      if (!errorFromServer) {
        setError("Live stream failed — loading via HTTP.");
        loadCandlesHttp();
      }
    };

    ws.onclose = () => {
      setLive(false);
      if (wsRef.current === ws) wsRef.current = null;
    };
    }, 400);

    return () => {
      clearTimeout(debounce);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [brokerConnected, symbol, timeframe, router, loadCandlesHttp, applyCandles]);

  useEffect(() => {
    if (brokerConnected !== true || live) return;

    const poll = () => {
      if (!live) void loadCandlesHttp(true);
    };
    const interval = setInterval(poll, CHART_HTTP_POLL_MS);
    return () => clearInterval(interval);
  }, [brokerConnected, live, symbol, timeframe, loadCandlesHttp]);

  return (
    <div className="min-h-screen bg-gray-950">
      <Navbar />
      <main className="max-w-6xl mx-auto px-4 py-8 space-y-6">
        <div className="flex items-center gap-3">
          <div>
            <h1 className="text-2xl font-bold">Charts</h1>
            <p className="text-gray-400 text-sm mt-0.5">
              Live OHLCV candlesticks from your connected broker
            </p>
          </div>
          {live && (
            <span className="flex items-center gap-1.5 text-xs text-success font-medium">
              <span className="w-2 h-2 rounded-full bg-success animate-pulse" />
              Live
            </span>
          )}
          {!live && brokerConnected && (
            <span className="text-xs text-gray-500">
              {error ? "Polling via HTTP" : "Connecting…"}
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-end gap-4">
          <div className="flex flex-col gap-2">
            <span className="text-sm text-gray-400">
              Symbol
              {symbolsLoading ? " (loading…)" : ` (${symbols.length} available)`}
            </span>
            <input
              type="text"
              placeholder="Search symbols…"
              value={symbolFilter}
              onChange={(e) => setSymbolFilter(e.target.value)}
              disabled={!brokerConnected || symbolsLoading}
              className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm w-44"
            />
            <select
              value={symbol}
              onChange={(e) => {
                hydratedRef.current = false;
                setSymbol(e.target.value);
              }}
              disabled={!brokerConnected || loading || symbolsLoading}
              size={Math.min(8, Math.max(4, filteredSymbols.length))}
              className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm min-w-[10rem] max-h-48"
            >
              {filteredSymbols.length === 0 ? (
                <option value={symbol}>{symbol}</option>
              ) : (
                filteredSymbols.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))
              )}
            </select>
          </div>

          <div className="flex flex-wrap gap-2">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                type="button"
                onClick={() => {
                  hydratedRef.current = false;
                  setTimeframe(tf);
                }}
                disabled={!brokerConnected || loading}
                className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 ${
                  timeframe === tf
                    ? "bg-brand text-white"
                    : "bg-gray-900 border border-gray-700 text-gray-300 hover:text-white"
                }`}
              >
                {tf}
              </button>
            ))}
          </div>

          {loading && <span className="text-sm text-gray-500">Connecting…</span>}
        </div>

        {error && (
          <p className="text-danger text-sm bg-red-950/50 rounded-lg px-4 py-2">
            {error}
            {brokerConnected === false && (
              <>
                {" "}
                <Link href="/connect" className="underline text-brand">
                  Connect broker
                </Link>
              </>
            )}
          </p>
        )}

        <div
          ref={containerRef}
          className="w-full rounded-2xl border border-gray-800 overflow-hidden min-h-[480px]"
        />
      </main>
    </div>
  );
}
