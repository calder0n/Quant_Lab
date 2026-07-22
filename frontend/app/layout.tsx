import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "QuantLab",
  description: "Quantitative research laboratory",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      {/* Browser extensions often inject classes/attributes on <body> before
          React hydrates; suppress the resulting attribute-mismatch warning. */}
      <body
        suppressHydrationWarning
        className="min-h-screen bg-[#0b0e14] text-slate-100 antialiased"
      >
        {children}
      </body>
    </html>
  );
}
