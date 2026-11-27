import "@fontsource-variable/bricolage-grotesque/opsz.css";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/600.css";
import "./globals.css";
import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "InterviewOps: Two requests. One slot.",
  description: "How a mock-interview booking stays correct when two requests arrive together, and where the guarantees stop.",
  icons: { icon: "/mark.svg" },
};
export const viewport: Viewport = { themeColor: "#06080f", colorScheme: "dark" };

// Decides motion and the opening before first paint, so neither flashes.
const early = `try{var d=document.documentElement,m=localStorage.getItem("io-motion"),r=matchMedia("(prefers-reduced-motion: reduce)").matches||(navigator.connection&&navigator.connection.saveData);var on=m?m==="on":!r;d.dataset.motion=on?"on":"off";var f=/bootSeek/.test(location.search);d.dataset.boot=on&&(f||(!sessionStorage.getItem("io-boot")&&!location.hash))?"running":"done"}catch(e){}`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" data-motion="off" data-boot="done" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: early }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
