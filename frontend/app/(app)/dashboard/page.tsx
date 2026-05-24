"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Navbar from "@/components/Navbar";
import { api } from "@/lib/api";
import { useDashboardStream } from "@/providers/DashboardStreamProvider";

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800">
      <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">{label}</p>
      <p className="text-2xl font-bold text-white">{value}</p>
      {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
    </div>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const {
    account,
    positions,
    botStatus,
    live,
    error,
    brokerConnected,
    setError,
  } = useDashboardStream();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!localStorage.getItem("token")) router.push("/login");
  }, [router]);

  async function toggleBot() {
    setError("");
    setLoading(true);
    try {
      if (botStatus?.running) await api.botStop();
      else await api.botStart();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Request failed";
      if (msg.includes("broker")) router.push("/connect");
      else setError(msg);
    } finally {
      setLoading(false);
    }
  }

  const isRunning = botStatus?.running ?? false;

  return (
    <div className="min-h-screen bg-gray-950">
      <Navbar />
      <main className="max-w-5xl mx-auto px-4 py-8 space-y-8">

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div>
              <h1 className="text-2xl font-bold">Dashboard</h1>
              <p className="text-gray-400 text-sm mt-0.5">
                {botStatus?.last_tick
                  ? `Last tick: ${new Date(botStatus.last_tick).toLocaleTimeString()}`
                  : "Bot not started"}
              </p>
            </div>
            {live && (
              <span className="flex items-center gap-1.5 text-xs text-success font-medium">
                <span className="w-2 h-2 rounded-full bg-success animate-pulse" />
                Live
              </span>
            )}
            {!live && account && (
              <span className="text-xs text-gray-500">Reconnecting…</span>
            )}
          </div>
          <button
            onClick={toggleBot}
            disabled={loading || brokerConnected === false}
            className={`px-6 py-2.5 rounded-xl font-semibold text-sm transition-all disabled:opacity-60 ${
              isRunning
                ? "bg-red-600 hover:bg-red-700 text-white"
                : "bg-brand hover:bg-brand-dark text-white"
            }`}
          >
            {loading ? "…" : isRunning ? "Stop Bot" : "Start Bot"}
          </button>
        </div>

        {error && <p className="text-danger text-sm bg-red-950/50 rounded-lg px-4 py-2">{error}</p>}

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Balance" value={account ? `${account.currency} ${account.balance.toLocaleString()}` : "—"} />
          <StatCard label="Equity" value={account ? `${account.currency} ${account.equity.toLocaleString()}` : "—"} />
          <StatCard label="Signals" value={String(botStatus?.total_signals ?? 0)} sub="this session" />
          <StatCard label="Trades Placed" value={String(botStatus?.trades_placed ?? 0)} sub="this session" />
        </div>

        <div className="flex items-center gap-3">
          <span className={`w-2.5 h-2.5 rounded-full ${isRunning ? "bg-success animate-pulse" : "bg-gray-600"}`} />
          <span className="text-sm text-gray-300">{isRunning ? "Bot is running" : "Bot is stopped"}</span>
          {isRunning && botStatus?.started_at && (
            <span className="text-xs text-gray-500">
              since {new Date(botStatus.started_at).toLocaleTimeString()}
            </span>
          )}
        </div>

        {(botStatus?.recent_errors?.length ?? 0) > 0 && (
          <div className="bg-red-950/30 border border-red-900 rounded-2xl p-5">
            <p className="text-sm font-semibold text-danger mb-2">Recent Errors</p>
            {botStatus!.recent_errors.map((e, i) => (
              <p key={i} className="text-xs text-gray-400 font-mono">{e}</p>
            ))}
          </div>
        )}

        <div>
          <h2 className="text-lg font-semibold mb-3">Open Positions</h2>
          {positions.length === 0 ? (
            <p className="text-gray-500 text-sm">No open positions.</p>
          ) : (
            <div className="overflow-x-auto rounded-2xl border border-gray-800">
              <table className="w-full text-sm">
                <thead className="bg-gray-900 text-gray-400">
                  <tr>
                    {["Symbol", "Direction", "Volume", "Open Price", "Current", "P&L"].map((h) => (
                      <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p) => (
                    <tr key={p.id} className="border-t border-gray-800 hover:bg-gray-900/50">
                      <td className="px-4 py-3 font-medium">{p.symbol}</td>
                      <td className={`px-4 py-3 font-semibold ${p.direction === "BUY" ? "text-success" : "text-danger"}`}>
                        {p.direction}
                      </td>
                      <td className="px-4 py-3">{p.volume}</td>
                      <td className="px-4 py-3">{p.open_price.toFixed(5)}</td>
                      <td className="px-4 py-3">{p.current_price.toFixed(5)}</td>
                      <td className={`px-4 py-3 font-semibold ${p.profit >= 0 ? "text-success" : "text-danger"}`}>
                        {p.profit >= 0 ? "+" : ""}{p.profit.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
