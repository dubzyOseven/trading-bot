"use client";

import { DashboardStreamProvider } from "@/providers/DashboardStreamProvider";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <DashboardStreamProvider>{children}</DashboardStreamProvider>;
}
