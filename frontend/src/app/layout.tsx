import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { getSession, isAdminEmail } from "@/lib/auth";
import TopBar from "./top-bar";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "erpSOFTapp Data Cleaner",
  description: "Upload Vendor, Customer, or Product data to clean and format for Odoo import.",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const session = await getSession();

  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {session && <TopBar email={session.email} isAdmin={isAdminEmail(session.email)} />}
        {children}
      </body>
    </html>
  );
}
