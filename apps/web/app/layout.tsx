import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Blostem",
  description: "Glass-box sales cockpit for Blostem's India-first BFSI pilot."
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
