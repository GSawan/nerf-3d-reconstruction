import type { Metadata } from "next";
import { Inter, Outfit, Bungee_Shade, Space_Grotesk } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const outfit = Outfit({ subsets: ["latin"], variable: "--font-outfit", weight: ["100", "400", "700", "900"] });
const bungeeShade = Bungee_Shade({ subsets: ["latin"], weight: "400", variable: "--font-bungee" });
const spaceGrotesk = Space_Grotesk({ subsets: ["latin"], variable: "--font-grotesk" });

export const metadata: Metadata = {
  title: "Neo3D Exhibition",
  description: "Experimental Digital Reconstruction",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} ${outfit.variable} ${bungeeShade.variable} ${spaceGrotesk.variable} bg-[#c8c8b6] text-zinc-900 min-h-screen antialiased flex flex-col`}>
        <main className="flex-1 flex flex-col">
          {children}
        </main>
      </body>
    </html>
  );
}
