'use client';

import { 
  LayoutDashboard, 
  PlusCircle, 
  Settings, 
  LogOut, 
  ShieldAlert, 
  Terminal, 
  Fingerprint,
  Zap,
  Menu,
  ChevronLeft
} from 'lucide-react';
import { useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import { clsx } from 'clsx';

const navItems = [
  { icon: LayoutDashboard, label: 'Dashboard', href: '/projects' },
  { icon: PlusCircle, label: 'New Project', href: '/projects/new' },
  { icon: Terminal, label: 'Intake Feed', href: '/intake' },
  { icon: ShieldAlert, label: 'Security Reports', href: '/reports' },
  { icon: Fingerprint, label: 'Agent Population', href: '/agents' },
  { icon: Settings, label: 'Settings', href: '/settings' },
];

export function Sidebar() {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const pathname = usePathname();
  const router = useRouter();

  const handleLogout = async () => {
    await fetch('/api/auth/logout', { method: 'POST' });
    router.push('/');
  };

  return (
    <motion.div
      initial={false}
      animate={{ width: isCollapsed ? 80 : 260 }}
      className="h-screen sticky top-0 bg-[rgba(10,10,12,0.8)] backdrop-blur-xl border-r border-[rgba(255,255,255,0.05)] flex flex-col z-50 overflow-hidden transition-all duration-500 ease-in-out"
    >
      {/* Brand Header */}
      <div className="h-20 flex items-center px-6 gap-3 mb-6 relative">
        <div className="w-10 h-10 shrink-0 bg-gradient-to-br from-[#8b5cf6] to-[#7c3aed] rounded-xl flex items-center justify-center shadow-[0_0_20px_rgba(139,92,246,0.2)]">
          <Zap className="text-white fill-white" size={20} />
        </div>
        {!isCollapsed && (
          <motion.div
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            className="flex flex-col"
          >
            <span className="text-xl font-bold tracking-tight">Breakpoint</span>
            <span className="text-[10px] text-[#8b5cf6] font-bold uppercase tracking-[0.2em]">Evolution Engine</span>
          </motion.div>
        )}
      </div>

      {/* Nav Items */}
      <div className="flex-grow flex flex-col gap-1 px-3">
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link key={item.href} href={item.href}>
              <div
                className={clsx(
                  'relative group flex items-center h-12 rounded-xl transition-all duration-300',
                  isActive 
                    ? 'bg-white/5 text-white shadow-inner' 
                    : 'text-[#64748b] hover:text-white hover:bg-white/[0.02]'
                )}
              >
                {/* Active Indicator */}
                {isActive && (
                  <motion.div
                    layoutId="active-pill"
                    className="absolute left-0 w-1 h-6 bg-[#8b5cf6] rounded-r-full shadow-[0_0_10px_#8b5cf6]"
                  />
                )}

                <div className={clsx('w-14 shrink-0 flex items-center justify-center', isActive ? 'text-[#8b5cf6]' : 'group-hover:text-[#8b5cf6]')}>
                  <item.icon size={20} strokeWidth={isActive ? 2.5 : 2} className="transition-transform group-hover:scale-110" />
                </div>

                {!isCollapsed && (
                  <span className="text-sm font-semibold tracking-wide">
                    {item.label}
                  </span>
                )}

                {/* Hover Glow Effect */}
                <div className="absolute inset-0 opacity-0 group-hover:opacity-100 bg-gradient-to-r from-[#8b5cf6]/5 to-transparent transition-opacity pointer-events-none rounded-xl" />
              </div>
            </Link>
          );
        })}
      </div>

      {/* User / Bottom Section */}
      <div className="p-4 flex flex-col gap-2">
        <button
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="h-10 w-full flex items-center rounded-xl hover:bg-white/5 transition-colors group"
        >
          <div className="w-12 shrink-0 flex items-center justify-center text-[#475569] group-hover:text-white">
            {isCollapsed ? <Menu size={20} /> : <ChevronLeft size={20} />}
          </div>
          {!isCollapsed && <span className="text-xs text-[#475569] font-bold uppercase tracking-widest group-hover:text-white">Collapse</span>}
        </button>

        <button
          onClick={handleLogout}
          className="h-10 w-full flex items-center rounded-xl hover:bg-[#ef4444]/5 text-[#ef4444]/60 hover:text-[#ef4444] transition-colors group"
        >
          <div className="w-12 shrink-0 flex items-center justify-center">
            <LogOut size={20} />
          </div>
          {!isCollapsed && <span className="text-xs font-bold uppercase tracking-widest">Logout</span>}
        </button>
      </div>
    </motion.div>
  );
}
