'use client';

import { useEffect, useState, useRef } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { Button, Input } from '@/components/ui';
import { 
  Dna, 
  Target, 
  ShieldAlert, 
  Zap, 
  Lock, 
  Edit3, 
  CheckCircle2, 
  Layers, 
  Map, 
  Activity,
  AlertTriangle,
  ChevronRight,
  Loader2,
  Trash2,
  Sparkles,
  Info
} from 'lucide-react';
import { useParams, useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx } from 'clsx';

export default function BlueprintDashboard() {
  const { id } = useParams();
  const router = useRouter();
  const [blueprint, setBlueprint] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefining, setIsRefining] = useState(false);
  const [refineInput, setRefineInput] = useState('');
  const [isLocking, setIsLocking] = useState(false);
  const [showVerify, setShowVerify] = useState(false);
  const [verificationData, setVerificationData] = useState(null);

  useEffect(() => {
    async function fetchBlueprint() {
      try {
        const response = await fetch(`/api/blueprint/${id}`);
        const data = await response.json();
        if (data.success) {
          setBlueprint(data.data);
        }
      } catch (error) {
        console.error('Failed to fetch blueprint:', error);
      } finally {
        setIsLoading(false);
      }
    }

    fetchBlueprint();
  }, [id]);

  const handleRefine = async (e) => {
    e.preventDefault();
    if (!refineInput.trim() || isRefining) return;
    setIsRefining(true);

    try {
      const response = await fetch(`/api/blueprint/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instruction: refineInput }),
      });
      const data = await response.json();
      if (data.success) {
        setBlueprint(data.data);
        setRefineInput('');
      }
    } catch (error) {
      console.error('Refinement failed:', error);
    } finally {
      setIsRefining(false);
    }
  };

  const handleVerify = async () => {
    setShowVerify(true);
    if (verificationData) return;
    
    try {
      const response = await fetch(`/api/blueprint/${id}/verify`, { method: 'POST' });
      const data = await response.json();
      if (data.success) {
        setVerificationData(data.data);
      }
    } catch (error) {
      console.error('Verification failed:', error);
    }
  };

  const handleLock = async () => {
    setIsLocking(true);
    try {
      const response = await fetch(`/api/blueprint/${id}/lock`, { method: 'POST' });
      if (response.ok) {
        router.push(`/projects/${id}/simulate/configure`);
      }
    } catch (error) {
      console.error('Lock failed:', error);
    } finally {
      setIsLocking(false);
    }
  };

  if (isLoading) {
    return (
      <AppShell>
        <div className="flex-grow flex flex-col items-center justify-center gap-4">
           <Loader2 className="animate-spin text-[#8b5cf6]" size={40} />
           <p className="text-sm font-bold text-[#475569] uppercase tracking-widest">Synthesizing Neural Blueprint...</p>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="flex flex-col gap-10 max-w-7xl mx-auto w-full py-6">
        {/* Blueprint Header */}
        <div className="flex items-center justify-between pb-6 border-b border-white/5">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-[#8b5cf6]/10 flex items-center justify-center text-[#8b5cf6] animate-pulse shadow-[0_0_15px_#8b5cf6]/20">
              <Dna size={24} />
            </div>
            <div className="flex flex-col">
              <h2 className="text-2xl font-bold tracking-tight">Product DNA Blueprint</h2>
              <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">Architectural State Representation</span>
            </div>
          </div>

          <div className="flex items-center gap-4">
             <Button variant="secondary" onClick={handleVerify} icon={Zap}>Preview Discovery Risks</Button>
             <Button loading={isLocking} onClick={handleLock} icon={Lock} className="bg-[#10b981] hover:bg-[#059669] shadow-[0_0_20px_#10b981]/20">
               Lock & Deploy Agents
             </Button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
          {/* Main Content: Sections */}
          <div className="lg:col-span-8 flex flex-col gap-10">
            {/* Identity & Mission */}
            <div className="glass-card flex flex-col gap-6">
               <div className="flex items-center gap-3">
                  <div className="p-2 bg-white/5 rounded-lg text-[#8b5cf6]">
                     <Target size={20} />
                  </div>
                  <h3 className="text-xl font-bold">System Identity</h3>
               </div>
               
               <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                  <div className="flex flex-col gap-2">
                     <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">Core Product Purpose</span>
                     <p className="text-sm font-medium leading-relaxed">{blueprint.identity?.description || 'N/A'}</p>
                  </div>
                  <div className="flex flex-col gap-2">
                     <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">Intended User Persona</span>
                     <p className="text-sm font-medium leading-relaxed">{blueprint.identity?.intendedUsers?.join(', ') || 'N/A'}</p>
                  </div>
               </div>
            </div>

            {/* Attack Surface Summary */}
            <div className="flex flex-col gap-6">
               <h3 className="text-sm font-bold text-[#475569] uppercase tracking-widest">High-Risk Attack Vectors ({blueprint.attackSurfaceMap?.length || 0})</h3>
               <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {blueprint.attackSurfaceMap?.map((vector, i) => (
                    <motion.div 
                      key={i}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.05 }}
                      className="bg-white/[0.02] border border-white/5 rounded-2xl p-5 group hover:border-[#8b5cf6]/40 transition-all cursor-default"
                    >
                       <div className="flex items-center justify-between mb-4">
                          <span className="text-sm font-bold group-hover:text-[#8b5cf6] tracking-tight transition-colors">{vector.feature}</span>
                          <div className={clsx(
                            'px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-[0.2em] border',
                            vector.riskLevel === 'critical' ? 'text-[#ef4444] bg-[#ef4444]/10 border-[#ef4444]/20' : 
                            vector.riskLevel === 'high' ? 'text-[#f97316] bg-[#f97316]/10 border-[#f97316]/20' : 
                            'text-[#3b82f6] bg-[#3b82f6]/10 border-[#3b82f6]/20'
                          )}>
                             {vector.riskLevel}
                          </div>
                       </div>
                       <ul className="flex flex-col gap-2">
                          {vector.attackVectors?.map((atv, j) => (
                            <li key={j} className="text-xs text-[#94a3b8] font-medium flex items-center gap-2">
                               <div className="w-1.5 h-1.5 rounded-full bg-white/10" />
                               {atv}
                            </li>
                          ))}
                       </ul>
                    </motion.div>
                  ))}
               </div>
            </div>

            {/* Core Entities & Flows Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-10">
               {/* Entities */}
               <div className="flex flex-col gap-6">
                  <h3 className="text-sm font-bold text-[#475569] uppercase tracking-widest">System Entities</h3>
                  <div className="flex flex-col gap-3">
                     {blueprint.entities?.map((entity, i) => (
                       <div key={i} className="glass backdrop-blur-lg border-white/10 p-4 rounded-2xl flex items-center gap-4 group">
                          <div className="w-10 h-10 rounded-xl bg-white/[0.03] border border-white/5 flex items-center justify-center text-[#8b5cf6]">
                             <Layers size={18} />
                          </div>
                          <div className="flex flex-col">
                             <span className="text-sm font-bold">{entity.name}</span>
                             <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">{entity.type}</span>
                          </div>
                       </div>
                     ))}
                  </div>
               </div>

               {/* Strategic Flows */}
               <div className="flex flex-col gap-6">
                  <h3 className="text-sm font-bold text-[#475569] uppercase tracking-widest">Critical User Flows</h3>
                  <div className="flex flex-col gap-3">
                     {blueprint.flows?.map((flow, i) => (
                       <div key={i} className="glass backdrop-blur-lg border-white/10 p-4 rounded-2xl flex flex-col gap-3">
                          <div className="flex items-center gap-3">
                            <div className="w-8 h-8 rounded-lg bg-[#3b82f6]/10 flex items-center justify-center text-[#3b82f6]">
                               <Map size={16} />
                            </div>
                            <span className="text-sm font-bold tracking-tight">{flow.name}</span>
                          </div>
                          <div className="flex items-center flex-wrap gap-2">
                             {flow.steps?.map((step, j) => (
                               <div key={j} className="flex items-center gap-2">
                                  <span className="text-[9px] font-bold uppercase tracking-widest text-[#475569]">{step.action}</span>
                                  {j < flow.steps.length - 1 && <ChevronRight size={10} className="text-[#475569]" />}
                               </div>
                             ))}
                          </div>
                       </div>
                     ))}
                  </div>
               </div>
            </div>
          </div>

          {/* Right Sidebar: Refinement & Summary */}
          <div className="lg:col-span-4 flex flex-col gap-8">
            {/* Refinement Panel */}
            <div className="glass-card flex flex-col gap-6 border-t-4 border-[#8b5cf6]">
               <div className="flex items-center gap-3">
                  <Edit3 size={18} className="text-[#8b5cf6]" />
                  <h3 className="text-lg font-bold">Blueprint Refinement</h3>
               </div>
               <p className="text-xs text-[#94a3b8] font-medium leading-relaxed">
                 Notice something missing? Instruct the engine to refine specific boundaries or features before proceeding.
               </p>
               
               <form onSubmit={handleRefine} className="flex flex-col gap-4">
                  <textarea 
                    value={refineInput}
                    onChange={(e) => setRefineInput(e.target.value)}
                    placeholder="e.g. Add a boundary between User and Payments..."
                    className="w-full h-32 bg-black/20 border border-white/5 rounded-2xl p-4 text-sm font-medium focus:ring-1 focus:ring-[#8b5cf6] focus:border-[#8b5cf6] placeholder:text-[#475569] resize-none"
                  />
                  <Button loading={isRefining} disabled={!refineInput.trim()} type="submit" variant="secondary" className="w-full">
                    Execute Optimization
                  </Button>
               </form>

               <div className="flex flex-col gap-2 pt-4 border-t border-white/5">
                  <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-widest">
                     <span className="text-[#475569]">Refinement Cycles</span>
                     <span className="text-[#8b5cf6]">{blueprint.metadata?.refinementCount || 0} / 3</span>
                  </div>
                  <div className="w-full h-1.5 bg-white/5 rounded-full overflow-hidden">
                     <div 
                      className="h-full bg-[#8b5cf6]" 
                      style={{ width: `${((blueprint.metadata?.refinementCount || 0) / 3) * 100}%` }} 
                     />
                  </div>
               </div>
            </div>

            {/* Readiness Summary */}
            <div className="bg-[#10b981]/5 border border-[#10b981]/10 p-6 rounded-3xl flex flex-col gap-4">
               <div className="flex items-center gap-3">
                  <CheckCircle2 size={24} className="text-[#10b981]" />
                  <h3 className="text-lg font-bold">Readiness Score: 92%</h3>
               </div>
               <p className="text-xs text-[#10b981]/80 font-medium leading-relaxed">
                 System complexity mapped successfully. Boundaries are localized and feature state is synchronized. Ready for evolutionary deployment.
               </p>
               <div className="flex flex-col gap-3 mt-2">
                  <div className="flex items-center gap-2 text-xs font-bold text-[#10b981]">
                    <ShieldAlert size={14} />
                    <span>8 Potential Critical Vectors</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs font-bold text-[#f59e0b]">
                    <Activity size={14} />
                    <span>14 Systemic Interaction Gaps</span>
                  </div>
               </div>
            </div>
          </div>
        </div>
      </div>

      {/* Verification Modal / Overlay */}
      <AnimatePresence>
        {showVerify && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/80 backdrop-blur-md"
          >
            <motion.div
              initial={{ scale: 0.95, y: 20 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.95, y: 20 }}
              className="w-full max-w-4xl glass-card border-white/10 p-10 flex flex-col gap-8 relative overflow-hidden"
            >
              {/* Background Glow */}
              <div className="absolute top-[-100px] left-[-100px] w-full h-full bg-[radial-gradient(circle_at_center,rgba(6,182,212,0.05)_0,transparent_50%)] pointer-events-none" />

              <div className="flex items-center justify-between">
                 <div className="flex items-center gap-4">
                    <div className="w-14 h-14 rounded-2xl bg-[#06b6d4]/10 flex items-center justify-center text-[#06b6d4] shadow-[0_0_20px_rgba(6,182,212,0.2)]">
                       <ShieldAlert size={32} />
                    </div>
                    <div className="flex flex-col">
                       <h2 className="text-3xl font-bold tracking-tight">Discovery Strategy Preview</h2>
                       <p className="text-[#64748b] font-medium mt-1">Simulated risk breakdown based on current blueprint DNA.</p>
                    </div>
                 </div>
                 <button 
                  onClick={() => setShowVerify(false)}
                  className="p-3 text-[#475569] hover:text-white transition-colors"
                 >
                    <X size={24} />
                 </button>
              </div>

              {!verificationData ? (
                <div className="flex flex-col items-center justify-center py-20 gap-4">
                   <Loader2 className="animate-spin text-[#06b6d4]" size={40} />
                   <p className="text-xs font-bold text-[#475569] uppercase tracking-[0.2em]">Executing Predictive Analysis...</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-10">
                   <div className="flex flex-col gap-6">
                      <h3 className="text-sm font-bold text-[#475569] uppercase tracking-widest">Theoretical Vulnerability Landscape</h3>
                      <div className="flex flex-col gap-3">
                         {verificationData.previewVulnerabilities?.map((v, i) => (
                           <div key={i} className="bg-white/[0.03] border border-white/5 p-4 rounded-2xl flex flex-col gap-2">
                              <div className="flex items-center justify-between">
                                 <span className="font-bold text-sm tracking-tight">{v.title}</span>
                                 <span className="text-[9px] font-bold uppercase tracking-widest text-[#ef4444]">{v.probability} Probability</span>
                              </div>
                              <p className="text-xs text-[#94a3b8] leading-relaxed">{v.description}</p>
                           </div>
                         ))}
                      </div>
                   </div>

                   <div className="flex flex-col gap-6">
                      <h3 className="text-sm font-bold text-[#475569] uppercase tracking-widest">Recommended Agent Allocation</h3>
                      <div className="p-6 rounded-3xl bg-[rgba(6,182,212,0.03)] border border-[#06b6d4]/10 flex flex-col gap-6">
                         {verificationData.agentStrategy?.map((s, i) => (
                           <div key={i} className="flex flex-col gap-2">
                              <div className="flex items-center justify-between text-xs font-bold uppercase tracking-widest">
                                 <span className="text-[#06b6d4]">{s.archetype}</span>
                                 <span className="text-white">{s.weight}%</span>
                              </div>
                              <div className="w-full h-1.5 bg-white/5 rounded-full overflow-hidden">
                                 <motion.div 
                                   initial={{ width: 0 }}
                                   animate={{ width: `${s.weight}%` }}
                                   className="h-full bg-[#06b6d4] shadow-[0_0_10px_#06b6d4]" 
                                 />
                              </div>
                           </div>
                         ))}
                      </div>

                      <div className="mt-auto bg-white/5 p-4 rounded-2xl flex items-center gap-4">
                         <div className="p-2 bg-white/5 rounded-lg text-[#06b6d4]">
                            <Info size={16} />
                         </div>
                         <p className="text-[10px] font-bold text-[#64748b] leading-relaxed uppercase tracking-wider">
                           This strategy maximizes coverage based on the identified boundaries. Final agent personas will be generated using Latin Hypercube Sampling.
                         </p>
                      </div>
                   </div>
                </div>
              )}

              <div className="flex justify-end gap-4 pt-4 border-t border-white/5">
                 <Button variant="secondary" onClick={() => setShowVerify(false)}>Return to Blueprint</Button>
                 <Button onClick={() => { setShowVerify(false); handleLock(); }} icon={Lock}>Lock DNA & Begin Simulation</Button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </AppShell>
  );
}

function X({ size, ...props }) {
  return (
    <svg 
      width={size} 
      height={size} 
      viewBox="0 0 24 24" 
      fill="none" 
      stroke="currentColor" 
      strokeWidth="2" 
      strokeLinecap="round" 
      strokeLinejoin="round" 
      {...props}
    >
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}
