"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Navbar from "@/components/Navbar";
import { api, BrokerStatus } from "@/lib/api";

const POPULAR_SERVERS = [
  "ICMarkets-Demo", "ICMarkets-Live01", "Pepperstone-Demo",
  "Pepperstone-Live", "XMGlobal-Demo 3", "Exness-Trial",
];

export default function ConnectPage() {
  const router = useRouter();
  const [status, setStatus] = useState<BrokerStatus | null>(null);
  const [form, setForm] = useState({ mt5_login: "", mt5_password: "", mt5_server: "", platform: "mt5" });
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.brokerStatus().then(setStatus).catch(() => {});
  }, []);

  async function handleConnect(e: React.FormEvent) {
    e.preventDefault();
    setError(""); setSuccess(""); setLoading(true);
    try {
      const result = await api.brokerConnect({ ...form, account_type: "cloud" });
      setStatus(result);
      setSuccess(`Connected! Balance: ${result.currency} ${result.balance?.toLocaleString()}`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleDisconnect() {
    if (!confirm("Disconnect your broker? This will stop your bot.")) return;
    setLoading(true);
    try {
      await api.brokerDisconnect();
      setStatus({ connected: false });
      setSuccess("Broker disconnected.");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-950">
      <Navbar />
      <main className="max-w-lg mx-auto px-4 py-10">
        <h1 className="text-2xl font-bold mb-1">Connect MT5 Account</h1>
        <p className="text-gray-400 text-sm mb-8">Your broker credentials are encrypted and stored securely.</p>

        {status?.connected && (
          <div className="bg-gray-900 border border-green-800 rounded-2xl p-6 mb-6">
            <div className="flex items-center gap-2 mb-3">
              <span className="w-2 h-2 rounded-full bg-success animate-pulse" />
              <span className="font-semibold text-success">Connected</span>
            </div>
            <div className="space-y-1 text-sm text-gray-300">
              <div>Login: <span className="text-white">{status.mt5_login}</span></div>
              <div>Server: <span className="text-white">{status.mt5_server}</span></div>
              <div>Balance: <span className="text-white">{status.currency} {status.balance?.toLocaleString()}</span></div>
              <div>Equity: <span className="text-white">{status.currency} {status.equity?.toLocaleString()}</span></div>
            </div>
            <button
              onClick={handleDisconnect} disabled={loading}
              className="mt-4 w-full border border-danger text-danger hover:bg-red-950/40 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              Disconnect Broker
            </button>
          </div>
        )}

        {!status?.connected && (
          <form onSubmit={handleConnect} className="bg-gray-900 rounded-2xl p-8 space-y-5 border border-gray-800">
            {error && <p className="text-danger text-sm bg-red-950/50 rounded-lg px-4 py-2">{error}</p>}
            {success && <p className="text-success text-sm bg-green-950/50 rounded-lg px-4 py-2">{success}</p>}

            <div>
              <label className="block text-sm text-gray-400 mb-1">MT5 Login Number</label>
              <input
                type="text" required value={form.mt5_login}
                onChange={(e) => setForm({ ...form, mt5_login: e.target.value })}
                placeholder="123456789"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1">MT5 Password</label>
              <input
                type="password" required value={form.mt5_password}
                onChange={(e) => setForm({ ...form, mt5_password: e.target.value })}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1">Broker Server</label>
              <input
                type="text" required value={form.mt5_server}
                onChange={(e) => setForm({ ...form, mt5_server: e.target.value })}
                list="servers" placeholder="ICMarkets-Demo"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand"
              />
              <datalist id="servers">
                {POPULAR_SERVERS.map((s) => <option key={s} value={s} />)}
              </datalist>
              <p className="text-xs text-gray-500 mt-1">Find your server name in MT5 → File → Open an Account</p>
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1">Platform</label>
              <select
                value={form.platform}
                onChange={(e) => setForm({ ...form, platform: e.target.value })}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand"
              >
                <option value="mt5">MetaTrader 5</option>
                <option value="mt4">MetaTrader 4</option>
              </select>
            </div>

            <p className="text-xs text-gray-500 bg-gray-800 rounded-lg p-3">
              By connecting, you authorise TradingBot to place trades on your behalf. Always use a demo account while testing.
            </p>

            <button
              type="submit" disabled={loading}
              className="w-full bg-brand hover:bg-brand-dark text-white font-semibold py-2.5 rounded-lg transition-colors disabled:opacity-60"
            >
              {loading ? "Connecting… (this can take ~30s)" : "Connect Account"}
            </button>
          </form>
        )}
      </main>
    </div>
  );
}
