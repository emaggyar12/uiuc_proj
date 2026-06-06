import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#17202a",
        panel: "#f8faf7",
        court: "#d88f45",
        line: "#d7ded6",
      },
      boxShadow: {
        soft: "0 10px 30px rgba(23, 32, 42, 0.08)",
      },
    },
  },
  plugins: [],
};

export default config;
