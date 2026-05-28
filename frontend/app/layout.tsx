import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MX-Trading Bot",
  description: "MX Academy automated MT5 trading platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
