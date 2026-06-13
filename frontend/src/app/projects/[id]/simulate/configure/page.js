'use client';

import { useState } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { Button } from '@/components/ui';
import { 
  Zap, 
  Target, 
  ShieldAlert, 
  Fingerprint, 
  ChevronRight, 
  Plus, 
  Sparkles,
  Search,
  Activity,
  Flame,
  Globe,
  Settings2
} from 'lucide-react';
import { useParams, useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx } from 'clsx';

const presets = [
  { id: 'light', name: 'Surface Scan', icon: Search, agents: 20, gens: 2, description: 'Rapid probing of core boundaries.', color: '#3b82f6' },
  { id: 'standard', name: 'Standard Probe', icon: Zap, agents: 50, gens: 5, description: 'Balanced evolutionary simulation.', color: '#8b5cf6' },
  { id: 'deep', name: 'Deep Discovery', icon: ShieldAlert, agents: 100, gens: 7, description: 'Complex systemic exploitation.', color: '#f59e0b' },
  { id: 'adversarial', name: 'Adversarial Siege', icon: Flame, agents: 150, gens: 10, description: 'Maximum intensity red-teaming.', color: '#ef4444' },
];

export default function SimulationConfigure() {
  const { id } = useParams();
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [intensity, setIntensity] = useState('standard');
  const [focusAreas, setFocusAreas] = useState([]);
  const [newFocus, setNewFocus] = useState('');

  const currentPreset = presets.find(p => p.id === intensity);

  const handleStart = async () => {
    setLoading(true);
    try {
      // 1. Configure
      const configRes = await fetch('/api/simulation/configure', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          projectId: id, 
          intensity, 
          focusAreas,
          totalAgents: currentPreset.agents,
          totalGenerations: currentPreset.gens
        }),
      });
      const configData = await configRes.json();
      const simId = configData.data._id;

      // 2. Start (fires in background)
      await fetch('/api/simulation/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ simulationId: simId }),
      });

      // 3. Redirect to live status
      router.push(`/projects/${id}/simulate/${simId}`);
    } catch (error) {
      console.error('Failed to start simulation:', error);
      setLoading(false);
    }
  };

  const toggleFocusArea = (area) => {
    if (focusAreas.includes(area)) {
      setFocusAreas(focusAreas.filter(a => a !== area));
    } else {
      setFocusAreas([...focusAreas, area]);
    }
  };

  const handleAddFocus = (e) => {
    e.preventDefault();
    if (newFocus.trim() && !focusAreas.includes(newFocus.trim())) {
      setFocusAreas([...focusAreas, newFocus.trim()]);
      setNewFocus('');
    }
  };

  return (
    <AppShell>
      <div className="max-w-4xl mx-auto w-full py-10">
        <div className="flex flex-col gap-10">
          <div className="flex flex-col gap-2">
            <h2 className="text-4xl font-bold tracking-tight">Configure Discovery</h2>
            <p className="text-[#64748b] font-medium leading-relaxed">Allocate agent resources and define evolutionary focus zones.</p>
          </div>

          {/* Intensity Selection */}
          <div className="flex flex-col gap-6">
             <h3 className="text-sm font-bold text-[#475569] uppercase tracking-widest flex items-center gap-2">
                <Activity size={14} className="text-[#8b5cf6]" /> Discovery Intensity
             </h3>
             <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {presets.map(p => (
                  <button
                    key={p.id}
                    onClick={() => setIntensity(p.id)}
                    className={clsx(
                      'p-5 rounded-3xl border transition-all flex flex-col gap-4 text-left group',
                      intensity === p.id 
                        ? 'bg-white/[0.03] border-[#8b5cf6] border-2 shadow-[0_0_30px_rgba(139,92,246,0.15)] scale-[1.02]' 
                        : 'bg-white/[0.02] border-white/5 hover:border-white/10'
                    )}
                  >
                     <div 
                      className="w-12 h-12 rounded-xl flex items-center justify-center transition-all duration-500"
                      style={{ 
                        backgroundColor: intensity === p.id ? `${p.color}20` : 'rgba(255,255,255,0.03)',
                        color: intensity === p.id ? p.color : '#475569'
                      }}
                     >
                        <p.icon size={24} />
                     </div>
                     <div className="flex flex-col">
                        <span className="font-bold text-sm tracking-tight">{p.name}</span>
                        <p className="text-[10px] text-[#475569] font-bold uppercase tracking-widest mt-1">
                          {p.agents} Agents • {p.gens} Gens
                        </p>
                     </div>
                  </button>
                ))}
             </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
             {/* Focus Areas */}
             <div className="lg:col-span-12 flex flex-col gap-6">
                <div className="glass-card flex flex-col gap-8">
                   <div className="flex items-center justify-between">
                     <h3 className="text-sm font-bold text-[#475569] uppercase tracking-widest flex items-center gap-2">
                        <Target size={14} className="text-[#3b82f6]" /> Prioritized Features
                     </h3>
                     <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest italic">Optional strategic focus</span>
                   </div>

                   <form onSubmit={handleAddFocus} className="flex gap-2">
                      <div className="flex-grow">
                        <input 
                          type="text" 
                          placeholder="Add custom feature focus..."
                          value={newFocus}
                          onChange={(e) => setNewFocus(e.target.value)}
                          className="w-full bg-[rgba(255,255,255,0.03)] border border-white/5 rounded-xl px-4 py-2.5 text-sm font-medium focus:ring-1 focus:ring-[#8b5cf6] focus:border-[#8b5cf6] placeholder:text-[#475569]"
                        />
                      </div>
                      <Button type="submit" variant="secondary" className="!px-4">Add Focus</Button>
                   </form>

                   <div className="flex flex-wrap gap-3">
                      {['User Auth', 'Payments', 'Data Privacy', 'API Integrity', 'Social Interaction'].map(f => (
                        <button
                          key={f}
                          onClick={() => toggleFocusArea(f)}
                          className={clsx(
                            'px-4 py-2 rounded-xl text-xs font-bold uppercase tracking-widest border transition-all',
                            focusAreas.includes(f) ? 'bg-[#8b5cf6]/10 border-[#8b5cf6] text-[#8b5cf6]' : 'bg-white/5 border-white/5 text-[#475569] hover:border-white/20'
                          )}
                        >
                          {f}
                        </button>
                      ))}
                      {focusAreas.filter(a => !['User Auth', 'Payments', 'Data Privacy', 'API Integrity', 'Social Interaction'].includes(a)).map(f => (
                         <button
                          key={f}
                          onClick={() => toggleFocusArea(f)}
                          className="px-4 py-2 rounded-xl text-xs font-bold uppercase tracking-widest border bg-[#8b5cf6]/10 border-[#8b5cf6] text-[#8b5cf6]"
                        >
                          {f}
                        </button>
                      ))}
                   </div>
                </div>
             </div>
          </div>

          <div className="glass-card flex flex-col gap-6 border-2 border-[#8b5cf6]/20 bg-[rgba(139,92,246,0.02)]">
             <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-[#8b5cf6]/10 flex items-center justify-center text-[#8b5cf6] shadow-[0_0_20px_rgba(139,92,246,0.2)]">
                   <Fingerprint size={24} />
                </div>
                <div className="flex flex-col">
                   <h3 className="text-xl font-bold">Infiltration Strategy Loaded</h3>
                   <p className="text-xs text-[#475569] font-bold uppercase tracking-widest">Natural selection engine initialized</p>
                </div>
             </div>

             <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-4 border-t border-white/5">
                <div className="flex flex-col gap-1">
                   <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">Total Agents</span>
                   <span className="text-lg font-bold">{currentPreset.agents} Deployed</span>
                </div>
                <div className="flex flex-col gap-1">
                   <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">Evolution Rounds</span>
                   <span className="text-lg font-bold">{currentPreset.gens} Iterations</span>
                </div>
                <div className="flex flex-col gap-1">
                   <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">Expected LLM Activity</span>
                   <span className="text-lg font-bold">{currentPreset.agents * currentPreset.gens}+ Calls</span>
                </div>
             </div>

             <p className="text-xs text-[#64748b] leading-relaxed font-medium italic">
                Strategic Note: Agents will be spawned using Latin Hypercube Sampling to maximize personality diversity across all 8 dimensions.
             </p>
          </div>

          <div className="flex justify-end gap-4">
             <Button variant="secondary" onClick={() => router.back()}>Abort</Button>
             <Button loading={loading} onClick={handleStart} icon={Sparkles} className="animate-glow">
                Deploy Agent Population
             </Button>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
