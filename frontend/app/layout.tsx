import type { Metadata } from "next";
import "./globals.css";
import "@/components/tasks/tasks.css";

export const metadata: Metadata = {
  title: "Alem — задачи бизнеса, практика для студентов",
  description: "Понятные задачи бизнеса, открытый каталог и квесты по вашим навыкам.",
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
    <html lang="ru">
      <body className="antialiased">{children}</body>
    </html>
  );
}
