import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Yūyake Finder",
  description: "夕焼け予測サービスの画面案",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
