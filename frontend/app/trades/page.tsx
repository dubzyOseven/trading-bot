"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Navbar from "@/components/Navbar";
import { api, Trade } from "@/lib/api";

export default function TradesPage() {
  const router = useRouter();
  const [trades, setTrades] = useState<Trade[]>([]);
  const [filter, setFilter] = useState<"ALL" | "OPEN" | "CLOSED">("ALL");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!localStorage.getItem("token")) { router.push("/login"); return; }
    api.history({ limit: 200 })
      .then(setTrades)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [router]);

  const filtered = filter === "ALL" ? trades : trades.filter((t) => t.status === filter);
  const totalPnl = filtered.reduce((sum, t) => sum + (t.profit ?? 0), 0);

  return (
    <div className="min-h-screen bg-gray-950">
      <Navbar />
      <main className="max-w-5xl mx-auto px-4 py-8 space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Trade History</h1>
          <span className={`text-lg font-bold ${totalPnl >= 0 ? "text-success" : "text-danger"}`}>
            Total P&L: {totalPnl >= 0 ? "+" : ""}{totalPnl.toFixed(2)}
          </span>
        </div>

        {/* Filter tabs */}
        <div className="flex gap-2">
          {(["ALL", "OPEN", "CLOSED"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                filter === f ? "bg-brand text-white" : "bg-gray-800 text-gray-400 hover:text-white"
              }`}
            >
              {f}
            </button>
          ))}
        </div>

        {loading ? (
          <p className="text-gray-400">Loading…</p>
        ) : filtered.length === 0 ? (
          <p className="text-gray-500 text-sm">No trades found.</p>
        ) : (
          <div className="overflow-x-auto rounded-2xl border border-gray-800">
            <table className="w-full text-sm">
              <thead className="bg-gray-900 text-gray-400">
                <tr>
                  {["Symbol", "Direction", "Volume", "Open Price", "Close Price", "P&L", "Status", "Opened"].map((h) => (
                    <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((t) => (
                  <tr key={t.id} className="border-t border-gray-800 hover:bg-gray-900/50">
                    <td className="px-4 py-3 font-medium">{t.symbol}</td>
                    <td className={`px-4 py-3 font-semibold ${t.direction === "BUY" ? "text-success" : "text-danger"}`}>
                      {t.direction}
                    </td>
                    <td className="px-4 py-3">{t.volume}</td>
                    <td className="px-4 py-3">{t.open_price.toFixed(5)}</td>
                    <td className="px-4 py-3">{t.close_price?.toFixed(5) ?? "—"}</td>
                    <td className={`px-4 py-3 font-semibold ${(t.profit ?? 0) >= 0 ? "text-success" : "text-danger"}`}>
                      {t.profit != null ? `${t.profit >= 0 ? "+" : ""}${t.profit.toFixed(2)}` : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                        t.status === "OPEN" ? "bg-blue-900/50 text-blue-300" : "bg-gray-800 text-gray-400"
                      }`}>
                        {t.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-400">{new Date(t.opened_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
