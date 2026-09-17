import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "COMPLYSCAN · Evidence-first compliance screening",
  description: "Traceable Legal Metrology packaged-commodity screening with applicability, evidence, and human review.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
