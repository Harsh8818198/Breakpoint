'use client';

import { useEffect, useState } from 'react';
import { Sidebar } from './Sidebar';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { Loader2 } from 'lucide-react';

export function AppShell({ children }) {
  const [isLoading, setIsLoading] = useState(true);
  const [user, setUser] = useState(null);
  const router = useRouter();

  useEffect(() => {
    async function checkAuth() {
      try {
        const response = await fetch('/api/auth/me');
        if (!response.ok) {
          router.push('/login');
          return;
        }
        const data = await response.json();
        setUser(data.data);
      } catch (error) {
        router.push('/login');
      } finally {
        setIsLoading(false);
      }
    }

    checkAuth();
  }, [router]);

  if (isLoading) {
    return (
      <div className="h-screen w-screen bg-[#050505] flex flex-col items-center justify-center gap-6">
        <div className="relative">
          <div className="w-20 h-20 border-4 border-[#8b5cf6]/10 rounded-full animate-pulse" />
          <div className="absolute inset-0 flex items-center justify-center">
            <Loader2 className="animate-spin text-[#8b5cf6]" size={32} />
          </div>
        </div>
        <div className="flex flex-col items-center">
          <h2 className="text-xl font-bold tracking-tight bg-gradient-to-r from-white to-[#64748b] bg-clip-text text-transparent">Initializing Systems</h2>
          <p className="text-xs text-[#475569] font-bold uppercase tracking-[0.2em] mt-1">Establishing Secure Connection</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-[#050505] text-[#f8fafc]">
      <Sidebar />
      <main className="flex-grow flex flex-col min-w-0">
        <header className="h-16 px-8 flex items-center justify-between border-b border-white/[0.05] bg-black/40 backdrop-blur-md sticky top-0 z-40">
          <div className="flex items-center gap-4">
            <h1 className="text-sm font-bold text-[#64748b] uppercase tracking-widest">Command Center</h1>
            <div className="h-4 w-px bg-white/10" />
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-[#10b981] animate-pulse shadow-[0_0_8px_#10b981]" />
              <span className="text-xs font-semibold text-[#10b981]">SYSTEM STABLE</span>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex flex-col items-end">
              <span className="text-sm font-bold">{user?.name || 'Commander'}</span>
              <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">{user?.role || 'Alpha Operator'}</span>
            </div>
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#8b5cf6]/20 to-[#7c3aed]/20 border border-[#8b5cf6]/30 flex items-center justify-center font-bold text-[#8b5cf6]">
              {user?.name?.[0] || 'U'}
            </div>
          </div>
        </header>

        <section className="flex-grow p-8 flex flex-col gap-8 max-w-[1600px] mx-auto w-full overflow-hidden">
          <AnimatePresence mode="wait">
            <motion.div
              key="content"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.4, ease: "easeOut" }}
              className="flex-grow flex flex-col gap-8"
            >
              {children}
            </motion.div>
          </AnimatePresence>
        </section>
      </main>

      {/* Global Background Particles (Simple Dots) */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute inset-0 bg-grid opacity-[0.2]" />
      </div>
    </div>
  );
}
