import "./globals.css";

export const metadata = {
  title: "Meiporul — Eye of Truth",
  description: "Follow English and Tamil news coverage across event timelines with Meiporul, Eye of Truth.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
