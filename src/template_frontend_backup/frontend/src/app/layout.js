import { Inter, Outfit } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: 'swap',
});

const outfit = Outfit({
  variable: "--font-outfit",
  subsets: ["latin"],
  display: 'swap',
});

export const metadata = {
  title: "PerspectiveLens - Tamil News Intelligence",
  description: "A computational perspective on Tamil Nadu news.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${inter.variable} ${outfit.variable}`} suppressHydrationWarning>
      <body style={{ fontFamily: 'var(--font-inter), sans-serif' }} suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
