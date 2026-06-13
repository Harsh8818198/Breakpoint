import { Inter, Outfit } from 'next/font/google';
import './globals.css';

const inter = Inter({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-inter',
});

const outfit = Outfit({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-outfit',
});

export const metadata = {
  title: {
    template: '%s | Breakpoint V2',
    default: 'Breakpoint V2 - AI Adversarial Testing',
  },
  description: 'The evolutionary simulation engine for discovery of product vulnerabilities.',
  icons: {
    icon: '/favicon.ico',
  },
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${inter.variable} ${outfit.variable}`}>
      <body className="bg-grid" suppressHydrationWarning={true}>
        <div className="min-h-screen relative flex flex-col">
          {/* Subtle Global Background Glow */}
          <div className="absolute top-0 left-0 w-full h-[500px] bg-gradient-to-b from-[rgba(139,92,246,0.03)] to-transparent pointer-events-none" />
          
          <main className="flex-grow z-10">
            {children}
          </main>

          {/* Fixed Background Decals */}
          <div className="fixed bottom-0 right-0 w-[600px] h-[600px] bg-[radial-gradient(circle_at_center,rgba(139,92,246,0.02)_0,transparent_70%)] pointer-events-none" />
          <div className="fixed top-0 left-0 w-[400px] h-[400px] bg-[radial-gradient(circle_at_center,rgba(6,182,212,0.01)_0,transparent_70%)] pointer-events-none" />
        </div>
      </body>
    </html>
  );
}
