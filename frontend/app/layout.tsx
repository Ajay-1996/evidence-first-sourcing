import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Clearcut — RFx Co-pilot",
  description: "A buyer-controlled workspace for RFx drafting, supplier evidence, normalized comparison and defensible award scenarios.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
