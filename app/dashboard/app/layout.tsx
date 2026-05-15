import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AirAlert · Utah PM2.5 Predictor",
  description:
    "An hourly air-quality outlook for elementary schools in three Utah cities. Built on OpenAQ, MLflow, FastAPI, and Next.js.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen text-slate-900 antialiased">
        {children}
      </body>
    </html>
  );
}
