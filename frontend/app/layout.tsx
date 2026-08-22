import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Prospector",
  description:
    "Prospecção de canais do YouTube para editores, thumbnail designers e agências. Grátis.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <head>
        {/*
          Applied before first paint so a dark-mode user never sees a white
          flash. Kept inline and tiny on purpose — a stored preference has to
          win over the OS setting, and that decision cannot wait for hydration.
        */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem("prospector.theme");if(t)document.documentElement.setAttribute("data-theme",t);}catch(e){}})();`,
          }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
