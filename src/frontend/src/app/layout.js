import "./globals.css";

export const metadata = {
  title: "Veritasium | English and Tamil News",
  description: "Follow English and Tamil news coverage across event timelines.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
