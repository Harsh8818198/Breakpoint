'use client';

import { useState } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { Button, Input } from '@/components/ui';
import { 
  Plus, 
  ChevronRight, 
  Cpu, 
  MessageSquare, 
  FileText, 
  GitBranch, 
  Sparkles,
  Zap,
  Globe
} from 'lucide-react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx } from 'clsx';

const modes = [
  { 
    id: 'conversation', 
    name: 'Interrogator', 
    icon: MessageSquare, 
    description: 'Multi-turn product Q&A to map identity and boundaries.',
    color: '#8b5cf6'
  },
  { 
    id: 'document', 
    name: 'Vault Parser', 
    icon: FileText, 
    description: 'Upload PRDs, API specs, and technical documentation.',
    color: '#3b82f6'
  },
  { 
    id: 'codebase', 
    name: 'Code Scanner', 
    icon: GitBranch, 
    description: 'Direct analysis of GitHub repositories and live URLs.',
    color: '#06b6d4'
  },
];

const providers = [
  { id: 'gemini', name: 'Google Gemini', icon: Sparkles, badge: 'Recommended' },
  { id: 'openai', name: 'OpenAI GPT-4', icon: Zap },
];

export default function NewProject() {
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const router = useRouter();

  const [formData, setFormData] = useState({
    name: '',
    mode: 'conversation',
    llmProvider: 'gemini',
    description: '',
  });

  const handleCreate = async () => {
    setLoading(true);
    setError('');

    try {
      const response = await fetch('/api/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.message || 'Failed to create project');
      }

      // Redirect to intake workflow
      const projectId = data.data._id;
      router.push(`/projects/${projectId}/intake/${formData.mode}`);
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  };

  return (
    <AppShell>
      <div className="max-w-4xl mx-auto w-full py-10">
        <div className="flex flex-col gap-10">
          {/* Header */}
          <div className="flex flex-col gap-2">
            <h2 className="text-4xl font-bold tracking-tight">New Adversarial Discovery</h2>
            <p className="text-[#64748b] font-medium leading-relaxed">Choose your intake vector to begin mapping the product ecosystem.</p>
          </div>

          {/* Stepper */}
          <div className="flex items-center gap-4">
             {[1,2,3].map(i => (
                <div key={i} className="flex items-center gap-4">
                  <div className={clsx(
                    'w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs transition-colors duration-500',
                    step >= i ? 'bg-[#8b5cf6] text-white' : 'bg-white/5 text-[#475569] border border-white/10'
                  )}>
                    {i}
                  </div>
                  {i < 3 && <div className={clsx('w-24 h-[1px] transition-colors duration-500', step > i ? 'bg-[#8b5cf6]' : 'bg-white/10')} />}
                </div>
             ))}
          </div>

          <AnimatePresence mode="wait">
            {step === 1 && (
              <motion.div
                key="step1"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="flex flex-col gap-8"
              >
                <div className="glass-card flex flex-col gap-8">
                  <h3 className="text-xl font-bold">Project Identity</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <Input 
                      label="Product Name" 
                      placeholder="e.g. Acme Marketplace" 
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    />
                    <Input 
                      label="Brief Description (Optional)" 
                      placeholder="High-level product goal..." 
                      value={formData.description}
                      onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    />
                  </div>

                  <div className="flex flex-col gap-4">
                    <label className="text-sm font-medium text-[#94a3b8]">AI Intelligence Engine</label>
                    <div className="grid grid-cols-2 gap-4">
                      {providers.map(p => (
                        <button
                          key={p.id}
                          onClick={() => setFormData({ ...formData, llmProvider: p.id })}
                          className={clsx(
                            'p-4 rounded-2xl border transition-all flex flex-col gap-3 text-left relative overflow-hidden group',
                            formData.llmProvider === p.id 
                              ? 'bg-[#8b5cf6]/5 border-[#8b5cf6] border-2 shadow-[0_0_20px_rgba(139,92,246,0.1)]' 
                              : 'bg-white/[0.02] border-white/5 hover:border-white/10'
                          )}
                        >
                          <div className="flex items-center justify-between">
                             <div className={clsx('p-2 rounded-xl bg-white/5', formData.llmProvider === p.id ? 'text-[#8b5cf6]' : 'text-[#475569]')}>
                                <p.icon size={20} />
                             </div>
                             {p.badge && (
                               <span className="text-[9px] font-bold uppercase tracking-widest bg-[#8b5cf6] text-white px-2 py-0.5 rounded-full">
                                  {p.badge}
                               </span>
                             )}
                          </div>
                          <span className="font-bold text-sm">{p.name}</span>
                          {formData.llmProvider === p.id && (
                            <motion.div layoutId="provider-check" className="absolute top-2 right-2 text-[#8b5cf6]">
                              <Plus className="rotate-45" size={14} />
                            </motion.div>
                          )}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="flex justify-end">
                  <Button 
                    disabled={!formData.name} 
                    onClick={() => setStep(2)}
                    icon={ChevronRight}
                  >
                    Select Intake Vector
                  </Button>
                </div>
              </motion.div>
            )}

            {step === 2 && (
              <motion.div
                key="step2"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="flex flex-col gap-8"
              >
                <div className="glass-card flex flex-col gap-8">
                  <h3 className="text-xl font-bold">Vector Selection</h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    {modes.map(m => (
                      <button
                        key={m.id}
                        onClick={() => setFormData({ ...formData, mode: m.id })}
                        className={clsx(
                          'p-6 rounded-3xl border transition-all flex flex-col items-center text-center gap-4 group relative',
                          formData.mode === m.id 
                            ? 'bg-white/[0.03] border-[#8b5cf6] border-2 shadow-[0_0_30px_rgba(139,92,246,0.15)] scale-[1.02]' 
                            : 'bg-white/[0.02] border-white/5 hover:border-white/10'
                        )}
                      >
                         <div 
                           className="w-14 h-14 rounded-2xl flex items-center justify-center transition-all duration-500 group-hover:scale-110"
                           style={{ 
                             backgroundColor: formData.mode === m.id ? `${m.color}20` : 'rgba(255,255,255,0.03)',
                             color: formData.mode === m.id ? m.color : '#475569'
                           }}
                         >
                            <m.icon size={28} />
                         </div>
                         <div className="flex flex-col">
                            <span className="font-bold text-lg">{m.name}</span>
                            <p className="text-xs text-[#475569] font-medium leading-relaxed mt-1 px-2">{m.description}</p>
                         </div>
                         {formData.mode === m.id && (
                           <div className="absolute top-4 right-4 text-[#8b5cf6]">
                              <Plus className="rotate-45" size={18} />
                           </div>
                         )}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex items-center justify-between">
                   <Button variant="secondary" onClick={() => setStep(1)}>Back</Button>
                   <Button onClick={() => setStep(3)} icon={ChevronRight}>Review Strategy</Button>
                </div>
              </motion.div>
            )}

            {step === 3 && (
              <motion.div
                key="step3"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="flex flex-col gap-8"
              >
                <div className="glass-card flex flex-col gap-8 border-2 border-[#8b5cf6]/20">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-xl bg-[#8b5cf6]/10 flex items-center justify-center text-[#8b5cf6]">
                      <Zap size={24} />
                    </div>
                    <div className="flex flex-col">
                      <h3 className="text-xl font-bold">Confirmation</h3>
                      <span className="text-xs text-[#475569] font-bold uppercase tracking-widest">Adversarial Strategy Loaded</span>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-8 py-4 border-y border-white/5">
                    <div className="flex flex-col gap-1">
                      <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">Target Product</span>
                      <span className="text-lg font-bold">{formData.name}</span>
                    </div>
                    <div className="flex flex-col gap-1">
                      <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">Intake Vector</span>
                      <span className="text-lg font-bold capitalize">{formData.mode}</span>
                    </div>
                    <div className="flex flex-col gap-1">
                       <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">Intelligence Layer</span>
                       <span className="text-lg font-bold capitalize">{formData.llmProvider}</span>
                    </div>
                    <div className="flex flex-col gap-1">
                       <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">Simulation Intensity</span>
                       <span className="text-lg font-bold">Standard (50 Agents)</span>
                    </div>
                  </div>

                  {error && <p className="text-sm text-[#ef4444] font-bold">{error}</p>}

                  <p className="text-sm text-[#64748b] leading-relaxed italic">
                    By initializing, the AI will begin decomposing your product features. 
                    Ensure all input data provided to the intake vector is accurate.
                  </p>
                </div>

                <div className="flex items-center justify-between">
                   <Button variant="secondary" onClick={() => setStep(2)}>Back</Button>
                   <Button loading={loading} onClick={handleCreate} icon={Sparkles}>Initialize Discovery</Button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </AppShell>
  );
}
