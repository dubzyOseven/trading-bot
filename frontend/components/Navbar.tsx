"use client";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { clearStreamCache } from "@/lib/streamCache";
import { useDashboardStreamOptional } from "@/providers/DashboardStreamProvider";
import { BrandLogo } from "@/components/BrandLogo";

const links = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/charts", label: "Charts" },
  { href: "/trades", label: "Trades" },
  { href: "/config", label: "Config" },
  { href: "/connect", label: "Broker" },
];

export default function Navbar() {
  const router = useRouter();
  const path = usePathname();
  const stream = useDashboardStreamOptional();

  function logout() {
    stream?.disconnect();
    clearStreamCache();
    localStorage.removeItem("token");
    router.push("/login");
  }

  return (
    <nav className="bg-gray-900 border-b border-gray-800 px-6 py-3 flex items-center gap-6">
      <BrandLogo size="sm" href="/dashboard" />
      <div className="flex gap-4 flex-1">
        {links.map((l) => (
          <Link
            key={l.href}
            href={l.href}
            className={`text-sm font-medium transition-colors ${
              path.startsWith(l.href)
                ? "text-white"
                : "text-gray-400 hover:text-white"
            }`}
          >
            {l.label}
          </Link>
        ))}
      </div>
      <button
        onClick={logout}
        className="text-sm text-gray-400 hover:text-white transition-colors"
      >
        Logout
      </button>
    </nav>
  );
}
