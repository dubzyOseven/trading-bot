"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const { access_token } = await api.register(email, password);
      localStorage.setItem("token", access_token);
      router.push("/connect");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 px-4">
      <div className="w-full max-w-md">
        <h1 className="text-3xl font-bold text-center mb-2 text-white">TradingBot</h1>
        <p className="text-center text-gray-400 mb-8">Create your account</p>
        <form onSubmit={handleSubmit} className="bg-gray-900 rounded-2xl p-8 space-y-5 border border-gray-800">
          {error && <p className="text-danger text-sm text-center bg-red-950/50 rounded-lg px-4 py-2">{error}</p>}
          <div>
            <label className="block text-sm text-gray-400 mb-1">Email</label>
            <input
              type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Password <span className="text-gray-500">(min 8 chars)</span></label>
            <input
              type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand"
            />
          </div>
          <button
            type="submit" disabled={loading}
            className="w-full bg-brand hover:bg-brand-dark text-white font-semibold py-2.5 rounded-lg transition-colors disabled:opacity-60"
          >
            {loading ? "Creating account…" : "Create Account"}
          </button>
          <p className="text-center text-sm text-gray-400">
            Already have an account?{" "}
            <Link href="/login" className="text-brand hover:underline">Sign in</Link>
          </p>
        </form>
      </div>
    </div>
  );
}
