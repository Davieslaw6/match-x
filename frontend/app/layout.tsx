import "./globals.css";
import type { ReactNode } from "react";
export const metadata = { title: "MATCH X", description: "Private football analysis assistant" };
const links = [["/", "Chat"], ["/matches", "Matches"], ["/tickets", "Tickets"], ["/history", "History"], ["/settings", "Settings"]] as const;
export default function Root({ children }: { children: ReactNode }) {
  return (
    <html lang="en" data-theme="dark">
      <body>
        <p className="notice">Outputs are statistical estimates, not advice or guarantees. Follow bookmaker terms and local law.</p>
        <main>{children}</main>
        <nav className="bottom" aria-label="Main">
          {links.map(([href, name]) => <a key={href} href={href}>{name}</a>)}
        </nav>
      </body>
    </html>
  );
}
