import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Roster Lab",
  description: "College basketball roster construction and transfer portal analytics.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
