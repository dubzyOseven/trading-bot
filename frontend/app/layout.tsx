import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TradingBot",
  description: "Automated MT5 Forex Trading Platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
