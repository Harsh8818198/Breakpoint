'use client';

import { motion } from 'framer-motion';
import { ShieldCheck, Zap, ArrowRight, ChevronRight, Target, Fingerprint, Lock, Layers } from 'lucide-react';
import Link from 'next/link';
import { Button } from '@/components/ui';

export default function Home() {
  const containerVariants = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: {
        staggerChildren: 0.15,
        delayChildren: 0.3,
      },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 30 },
    show: { opacity: 1, y: 0, transition: { duration: 0.8, ease: "easeOut" } },
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#050505] overflow-hidden">
      {/* Dynamic Background Glows */}
      <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-[#8b5cf6] rounded-full blur-[200px] opacity-[0.03] animate-pulse" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] bg-[#06b6d4] rounded-full blur-[200px] opacity-[0.03] animate-pulse" />

      {/* Navigation Header */}
      <nav className="h-20 px-8 flex items-center justify-between border-b border-white/5 relative z-50">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-[#8b5cf6] to-[#7c3aed] rounded-xl flex items-center justify-center shadow-[0_0_20px_rgba(139,92,246,0.3)]">
            <Zap className="text-white fill-white" size={20} />
          </div>
          <span className="text-2xl font-bold tracking-tighter">Breakpoint <span className="text-[#8b5cf6]">V2</span></span>
        </div>
        <div className="flex items-center gap-6">
          <Link href="/projects" className="text-sm font-bold text-[#64748b] hover:text-white transition-colors uppercase tracking-widest px-4 py-2 hover:bg-white/5 rounded-xl">Dashboard</Link>
          <Link href="/projects">
            <Button className="!px-6 !py-2.5" icon={ArrowRight}>Get Started</Button>
          </Link>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="flex-grow flex flex-col items-center justify-center text-center px-6 relative z-10 py-32">
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="show"
          className="max-w-4xl flex flex-col items-center gap-8"
        >
          <motion.div
            variants={itemVariants}
            className="px-4 py-1.5 rounded-full border border-[#8b5cf6]/30 bg-[#8b5cf6]/5 text-[#8b5cf6] text-[10px] font-bold uppercase tracking-[0.3em] flex items-center gap-2"
          >
            <ShieldCheck size={14} className="animate-pulse" />
            Adversarial Discovery Protocol Active
          </motion.div>

          <motion.h1
            variants={itemVariants}
            className="text-6xl md:text-8xl font-black tracking-tighter leading-[0.9] bg-gradient-to-b from-white to-[#94a3b8] bg-clip-text text-transparent"
          >
            Engineer Product <br /> 
            <span className="text-[#8b5cf6] drop-shadow-[0_0_30px_rgba(139,92,246,0.3)]">DNA Integrity</span>
          </motion.h1>

          <motion.p
            variants={itemVariants}
            className="text-[#64748b] text-lg md:text-xl font-medium max-w-2xl leading-relaxed"
          >
            The world's first evolutionary simulation engine for discovery. 
            Adversarial agents mutating across 5 generations to find what you missed.
          </motion.p>

          <motion.div
            variants={itemVariants}
            className="flex items-center justify-center gap-6 mt-4"
          >
            <Link href="/projects">
              <Button className="!px-10 !py-4 !text-lg" icon={Zap}>Initialize Discovery</Button>
            </Link>
            <Link href="/docs">
              <Button variant="secondary" className="!px-8 !py-4" icon={ChevronRight}>View Architecture</Button>
            </Link>
          </motion.div>
        </motion.div>

        {/* Floating Feature Icons with lines */}
        <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 pointer-events-none opacity-[0.4]">
           <div className="flex items-center justify-between px-20">
              <motion.div animate={{ y: [0, -20, 0] }} transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }} className="w-16 h-16 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center text-[#8b5cf6]">
                 <Target size={32} />
              </motion.div>
              <motion.div animate={{ y: [0, 20, 0] }} transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }} className="w-16 h-16 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center text-[#06b6d4]">
                 <Fingerprint size={32} />
              </motion.div>
           </div>
        </div>
      </section>

      {/* Feature Grid Summary */}
      <section className="py-32 px-8 border-t border-white/5 bg-[rgba(255,255,255,0.01)]">
        <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-12">
           {[
             { title: 'Neural Decomp', icon: Layers, desc: '3-mode intake vectors using switchable LLM abstractions for comprehensive product identity mapping.' },
             { title: 'Evolutionary Loop', icon: Zap, desc: '5 unique generations of adversarial probing. Each round mutates strategy based on previous successes.' },
             { title: 'Forensic Intelligence', icon: Lock, desc: 'High-resolution discovery reports featuring BSS severity scoring and phylogenetic mutation trees.' },
           ].map((f, i) => (
             <div key={i} className="flex flex-col gap-6 group">
                <div className="w-14 h-14 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center text-[#8b5cf6] transition-all duration-500 group-hover:scale-110 group-hover:border-[#8b5cf6]/30">
                   <f.icon size={28} />
                </div>
                <div className="flex flex-col gap-2">
                   <h3 className="text-xl font-bold tracking-tight text-white">{f.title}</h3>
                   <p className="text-sm text-[#475569] font-medium leading-relaxed">{f.desc}</p>
                </div>
             </div>
           ))}
        </div>
      </section>

      {/* Final Call to action */}
      <footer className="py-20 flex flex-col items-center justify-center border-t border-white/5 bg-black relative">
         <div className="absolute top-0 w-full h-px bg-gradient-to-r from-transparent via-[#8b5cf6]/30 to-transparent" />
         <div className="flex flex-col items-center gap-8 text-center max-w-2xl px-6">
            <h2 className="text-4xl font-bold tracking-tighter">Ready for <span className="text-[#8b5cf6]">Infiltration?</span></h2>
            <p className="text-[#64748b] font-medium uppercase tracking-widest text-[10px]">Trusted by elite teams across the multiverse.</p>
            <Link href="/projects">
              <Button icon={Zap}>Begin Discovery Session</Button>
            </Link>
         </div>
         <div className="mt-20 flex items-center gap-10 text-[10px] text-[#334155] font-bold uppercase tracking-[0.3em]">
            <span>© 2026 BREAKPOINT V2</span>
            <div className="w-1 h-1 bg-white/10 rounded-full" />
            <span>NEURAL NETWORK OPERATIONAL</span>
         </div>
      </footer>
    </div>
  );
}
