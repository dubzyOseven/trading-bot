"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Navbar from "@/components/Navbar";
import { api, BotConfig } from "@/lib/api";

const TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"];

const STRATEGIES = [
  {
    value: "ema_crossover",
    label: "EMA Crossover + RSI Filter",
    description: "Trades when fast EMA crosses slow EMA. Low frequency — best on 1h/4h.",
    freq: "Low",
    freqColor: "text-blue-400",
  },
  {
    value: "rsi_oscillator",
    label: "RSI Oscillator",
    description: "Buys when RSI bounces out of oversold (<30), sells out of overbought (>70). High frequency on 1m/5m.",
    freq: "High",
    freqColor: "text-green-400",
  },
  {
    value: "macd",
    label: "MACD Histogram + Trend Filter",
    description: "Trades when MACD histogram changes direction, filtered by EMA(50) trend. Medium-high frequency.",
    freq: "Medium-High",
    freqColor: "text-yellow-400",
  },
];

function Field({
  label, name, value, onChange, min, max, step, hint,
}: {
  label: string; name: string; value: number;
  onChange: (v: string) => void; min?: number; max?: number; step?: number; hint?: string;
}) {
  return (
    <div>
      <label className="block text-sm text-gray-400 mb-1">{label}</label>
      <input
        type="number" name={name} value={value} min={min} max={max} step={step}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand"
      />
      {hint && <p className="text-xs text-gray-500 mt-1">{hint}</p>}
    </div>
  );
}

export default function ConfigPage() {
  const router = useRouter();
  const [cfg, setCfg] = useState<BotConfig>({
    symbol: "XAUUSD", timeframe: "1m", strategy_name: "ema_crossover",
    risk_percent: 1.0, max_open_trades: 3, atr_multiplier_sl: 1.5,
    atr_multiplier_tp: 2.5, ema_fast: 9, ema_slow: 21, rsi_period: 14,
    rsi_overbought: 70, rsi_oversold: 30,
  });
  const [success, setSuccess] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!localStorage.getItem("token")) { router.push("/login"); return; }
    api.getConfig().then(setCfg).catch(() => {});
  }, [router]);

  function setNum(key: keyof BotConfig, value: string) {
    setCfg((prev) => ({ ...prev, [key]: Number(value) }));
  }
  function setStr(key: keyof BotConfig, value: string) {
    setCfg((prev) => ({ ...prev, [key]: value }));
  }

  const selectedStrategy = STRATEGIES.find((s) => s.value === cfg.strategy_name);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setError(""); setSuccess(""); setLoading(true);
    try {
      await api.updateConfig(cfg);
      setSuccess("Saved — takes effect on the next tick.");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-950">
      <Navbar />
      <main className="max-w-xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold mb-1">Strategy Configuration</h1>
        <p className="text-gray-400 text-sm mb-8">Changes take effect on the next scheduled tick.</p>

        <form onSubmit={handleSave} className="space-y-6">
          {error && <p className="text-danger text-sm bg-red-950/50 rounded-lg px-4 py-2">{error}</p>}
          {success && <p className="text-success text-sm bg-green-950/50 rounded-lg px-4 py-2">{success}</p>}

          {/* Strategy selector */}
          <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 space-y-3">
            <p className="text-sm font-semibold text-gray-300 uppercase tracking-wide">Strategy</p>
            {STRATEGIES.map((s) => (
              <label
                key={s.value}
                className={`flex items-start gap-3 p-3 rounded-xl cursor-pointer border transition-colors ${
                  cfg.strategy_name === s.value
                    ? "border-brand bg-indigo-950/30"
                    : "border-gray-800 hover:border-gray-600"
                }`}
              >
                <input
                  type="radio" name="strategy_name" value={s.value}
                  checked={cfg.strategy_name === s.value}
                  onChange={(e) => setStr("strategy_name", e.target.value)}
                  className="mt-0.5 accent-brand"
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-white">{s.label}</span>
                    <span className={`text-xs font-semibold ${s.freqColor}`}>
                      {s.freq} freq
                    </span>
                  </div>
                  <p className="text-xs text-gray-400 mt-0.5">{s.description}</p>
                </div>
              </label>
            ))}
          </div>

          {/* Instrument */}
          <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 space-y-4">
            <p className="text-xs uppercase text-gray-500 tracking-wide font-semibold">Instrument</p>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Symbol</label>
              <input
                type="text" value={cfg.symbol}
                onChange={(e) => setStr("symbol", e.target.value.toUpperCase())}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Timeframe</label>
              <select
                value={cfg.timeframe} onChange={(e) => setStr("timeframe", e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand"
              >
                {TIMEFRAMES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              {cfg.strategy_name === "rsi_oscillator" && cfg.timeframe === "1h" && (
                <p className="text-xs text-yellow-400 mt-1">Tip: RSI Oscillator works best on 1m–15m for higher signal frequency.</p>
              )}
            </div>
          </div>

          {/* Risk */}
          <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 space-y-4">
            <p className="text-xs uppercase text-gray-500 tracking-wide font-semibold">Risk Management</p>
            <Field label="Risk Per Trade (%)" name="risk_percent" value={cfg.risk_percent}
              onChange={(v) => setNum("risk_percent", v)} min={0.1} max={10} step={0.1}
              hint="% of account equity risked per trade" />
            <Field label="Max Open Trades" name="max_open_trades" value={cfg.max_open_trades}
              onChange={(v) => setNum("max_open_trades", v)} min={1} max={20} />
            <Field label="ATR Stop-Loss Multiplier" name="atr_multiplier_sl" value={cfg.atr_multiplier_sl}
              onChange={(v) => setNum("atr_multiplier_sl", v)} min={0.5} max={5} step={0.1} />
            <Field label="ATR Take-Profit Multiplier" name="atr_multiplier_tp" value={cfg.atr_multiplier_tp}
              onChange={(v) => setNum("atr_multiplier_tp", v)} min={0.5} max={10} step={0.1} />
          </div>

          {/* RSI params — shown for rsi_oscillator and ema_crossover */}
          {(cfg.strategy_name === "rsi_oscillator" || cfg.strategy_name === "ema_crossover") && (
            <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 space-y-4">
              <p className="text-xs uppercase text-gray-500 tracking-wide font-semibold">RSI Parameters</p>
              <Field label="RSI Period" name="rsi_period" value={cfg.rsi_period}
                onChange={(v) => setNum("rsi_period", v)} min={2} max={50} />
              <Field label="Overbought Level" name="rsi_overbought" value={cfg.rsi_overbought}
                onChange={(v) => setNum("rsi_overbought", v)} min={50} max={95} step={1}
                hint="Sell signal fires when RSI crosses below this" />
              <Field label="Oversold Level" name="rsi_oversold" value={cfg.rsi_oversold}
                onChange={(v) => setNum("rsi_oversold", v)} min={5} max={50} step={1}
                hint="Buy signal fires when RSI crosses above this" />
            </div>
          )}

          {/* EMA params — shown for ema_crossover and macd */}
          {cfg.strategy_name === "ema_crossover" && (
            <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 space-y-4">
              <p className="text-xs uppercase text-gray-500 tracking-wide font-semibold">EMA Parameters</p>
              <Field label="Fast EMA Period" name="ema_fast" value={cfg.ema_fast}
                onChange={(v) => setNum("ema_fast", v)} min={2} max={50} />
              <Field label="Slow EMA Period" name="ema_slow" value={cfg.ema_slow}
                onChange={(v) => setNum("ema_slow", v)} min={5} max={200} />
            </div>
          )}

          <button
            type="submit" disabled={loading}
            className="w-full bg-brand hover:bg-brand-dark text-white font-semibold py-2.5 rounded-xl transition-colors disabled:opacity-60"
          >
            {loading ? "Saving…" : "Save Configuration"}
          </button>
        </form>
      </main>
    </div>
  );
}
