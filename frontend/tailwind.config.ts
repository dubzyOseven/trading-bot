import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "#6366f1", dark: "#4f46e5" },
        success: "#22c55e",
        danger: "#ef4444",
      },
    },
  },
  plugins: [],
};
export default config;
