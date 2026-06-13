'use client';

import { useEffect, useState, useRef } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { Button } from '@/components/ui';
import {
  Send,
  Bot,
  User,
  Sparkles,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Shield,
  Zap,
  Users,
} from 'lucide-react';
import { useParams, useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx } from 'clsx';

// Round theme metadata
const ROUND_THEMES = {
  1: { label: 'Authentication & Identity', icon: Shield, color: '#8b5cf6' },
  2: { label: 'Pricing, Limits & Enforcement', icon: Zap, color: '#f59e0b' },
  3: { label: 'Social Dynamics & Data Ownership', icon: Users, color: '#06b6d4' },
};

/**
 * Renders message content with basic markdown-style formatting:
 * - **bold** → <strong>
 * - Dashes at line start → visual bullet
 * - Newlines → line breaks
 */
function MessageContent({ content }) {
  const lines = content.split('\n');

  return (
    <div className="leading-relaxed space-y-1.5 whitespace-pre-wrap">
      {lines.map((line, i) => {
        const trimmed = line.trim();

        // Bullet line
        if (trimmed.startsWith('- ') || trimmed.startsWith('• ')) {
          const text = trimmed.slice(2);
          return (
            <div key={i} className="flex gap-2 items-start">
              <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-[#8b5cf6]/60 shrink-0" />
              <span className="flex-1">{renderInline(text)}</span>
            </div>
          );
        }

        // Empty line → spacing
        if (!trimmed) return <div key={i} className="h-1" />;

        return <div key={i}>{renderInline(trimmed)}</div>;
      })}
    </div>
  );
}

/**
 * Renders inline bold (**text**) within a line
 */
function renderInline(text) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} className="font-bold text-white">{part.slice(2, -2)}</strong>;
    }
    return <span key={i}>{part}</span>;
  });
}

export default function ConversationIntake() {
  const { id } = useParams();
  const router = useRouter();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSending, setIsSending] = useState(false);
  const [round, setRound] = useState(0);
  const [isDone, setIsDone] = useState(false);
  const [isBlueprintLoading, setIsBlueprintLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showTimeoutNotice, setShowTimeoutNotice] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const timeoutRef = useRef(null);

  // Start the conversation on mount
  useEffect(() => {
    async function startConversation() {
      try {
        const response = await fetch('/api/intake/conversation/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ projectId: id }),
        });
        const data = await response.json();
        if (data.success) {
          const convo = data.data;
          setConversationId(convo._id);
          setMessages(convo.messages || []);
          setRound(convo.followUpRound || 0);
        }
      } catch (err) {
        console.error('Failed to start conversation:', err);
      } finally {
        setIsLoading(false);
      }
    }
    startConversation();
  }, [id]);

  // Auto-scroll to bottom whenever messages change
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isSending]);

  // Auto-focus input after sending
  useEffect(() => {
    if (!isSending && !isDone && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isSending, isDone]);

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!input.trim() || isSending || isDone || !conversationId) return;

    const userMessage = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage, metadata: { type: 'user_input' } }]);
    setIsSending(true);

    try {
      const response = await fetch('/api/intake/conversation/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conversationId, message: userMessage }),
      });
      const data = await response.json();

      if (data.success) {
        const convo = data.data.conversation;
        setMessages(convo.messages || []);
        setRound(data.data.followUpRound || round);
        if (data.data.isComplete) {
          setIsDone(true);
        }
      } else {
        console.error('Message failed:', data.message);
      }
    } catch (err) {
      console.error('Failed to send message:', err);
    } finally {
      setIsSending(false);
    }
  };

  const handleGenerateBlueprint = async () => {
    setIsBlueprintLoading(true);
    setError(null);
    setShowTimeoutNotice(false);

    timeoutRef.current = setTimeout(() => {
      setShowTimeoutNotice(true);
    }, 90000);

    try {
      const response = await fetch('/api/intake/conversation/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ projectId: id }),
      });
      const data = await response.json();

      if (data.success) {
        router.push(`/projects/${id}/blueprint`);
      } else {
        throw new Error(data.message || 'Blueprint generation failed');
      }
    } catch (err) {
      console.error('Failed to generate blueprint:', err);
      setError('The synthesis engine hit a validation error. Usually happens with very complex products. Try again.');
      setIsBlueprintLoading(false);
    } finally {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    }
  };

  if (isLoading && messages.length === 0) {
    return (
      <AppShell>
        <div className="flex-grow flex flex-col items-center justify-center gap-4">
          <Loader2 className="animate-spin text-[#8b5cf6]" size={40} />
          <p className="text-sm font-bold text-[#475569] uppercase tracking-widest">
            Initializing Interrogator...
          </p>
        </div>
      </AppShell>
    );
  }

  const currentTheme = ROUND_THEMES[round] || null;
  const progressPct = Math.min((round / 3) * 100, 100);

  return (
    <AppShell>
      <div className="flex-grow flex flex-col gap-0 max-h-[calc(100vh-120px)] overflow-hidden">

        {/* Header */}
        <div className="flex items-center justify-between px-1 pb-4 border-b border-white/[0.05] mb-4 shrink-0">
          <div className="flex items-center gap-4">
            <div className="w-11 h-11 rounded-xl bg-[#8b5cf6]/10 border border-[#8b5cf6]/20 flex items-center justify-center text-[#8b5cf6]">
              <Bot size={22} />
            </div>
            <div className="flex flex-col">
              <h2 className="text-lg font-bold tracking-tight">Product Interrogator</h2>
              <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">
                Mode 1 — Conversational Intake
              </span>
            </div>
          </div>

          <div className="flex items-center gap-5">
            {/* Round progress */}
            <div className="flex flex-col items-end gap-1.5">
              <div className="flex items-center gap-2">
                {currentTheme && (
                  <span className="text-[10px] font-bold uppercase tracking-widest" style={{ color: currentTheme.color }}>
                    {currentTheme.label}
                  </span>
                )}
                <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">
                  Round {Math.min(round, 3)}/3
                </span>
              </div>
              <div className="w-36 h-1 bg-white/[0.05] rounded-full overflow-hidden">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${progressPct}%` }}
                  transition={{ duration: 0.5 }}
                  className="h-full rounded-full"
                  style={{ background: currentTheme?.color || '#8b5cf6', boxShadow: `0 0 8px ${currentTheme?.color || '#8b5cf6'}` }}
                />
              </div>
            </div>

            {isDone && (
              <Button
                loading={isBlueprintLoading}
                onClick={handleGenerateBlueprint}
                icon={Sparkles}
              >
                Construct Blueprint
              </Button>
            )}
          </div>
        </div>

        {/* Chat area */}
        <div
          ref={scrollRef}
          className="flex-grow overflow-y-auto flex flex-col gap-5 pr-2 custom-scrollbar"
        >
          <AnimatePresence initial={false}>
            {messages.map((msg, i) => {
              const isUser = msg.role === 'user';
              const theme = msg.metadata?.round ? ROUND_THEMES[msg.metadata.round] : null;

              return (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 8, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  transition={{ duration: 0.25 }}
                  className={clsx(
                    'flex gap-3 max-w-[80%]',
                    isUser ? 'self-end flex-row-reverse' : 'self-start'
                  )}
                >
                  {/* Avatar */}
                  <div className={clsx(
                    'w-8 h-8 rounded-lg shrink-0 flex items-center justify-center mt-0.5',
                    isUser
                      ? 'bg-[#3b82f6]/10 border border-[#3b82f6]/20 text-[#3b82f6]'
                      : 'bg-[#8b5cf6]/10 border border-[#8b5cf6]/20 text-[#8b5cf6]'
                  )}>
                    {isUser ? <User size={14} /> : <Bot size={14} />}
                  </div>

                  {/* Bubble */}
                  <div className="flex flex-col gap-1.5">
                    {/* Theme badge for follow-up rounds */}
                    {!isUser && theme && (
                      <div
                        className="self-start flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-widest"
                        style={{
                          color: theme.color,
                          backgroundColor: `${theme.color}15`,
                          border: `1px solid ${theme.color}30`,
                        }}
                      >
                        <theme.icon size={9} />
                        {theme.label}
                      </div>
                    )}

                    <div className={clsx(
                      'px-4 py-3 rounded-2xl text-sm shadow-lg',
                      isUser
                        ? 'bg-[#3b82f6]/8 border border-[#3b82f6]/12 text-white'
                        : 'bg-white/[0.04] border border-white/[0.07] text-[#e2e8f0]'
                    )}>
                      <MessageContent content={msg.content} />
                    </div>
                  </div>
                </motion.div>
              );
            })}

            {/* Typing indicator */}
            {isSending && (
              <motion.div
                key="typing"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="flex gap-3 self-start"
              >
                <div className="w-8 h-8 rounded-lg shrink-0 flex items-center justify-center bg-[#8b5cf6]/10 border border-[#8b5cf6]/20 text-[#8b5cf6]">
                  <Sparkles size={14} className="animate-pulse" />
                </div>
                <div className="px-4 py-3 rounded-2xl bg-white/[0.04] border border-white/[0.07] flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 bg-[#8b5cf6] rounded-full animate-bounce [animation-delay:-0.3s]" />
                  <span className="w-1.5 h-1.5 bg-[#8b5cf6] rounded-full animate-bounce [animation-delay:-0.15s]" />
                  <span className="w-1.5 h-1.5 bg-[#8b5cf6] rounded-full animate-bounce" />
                </div>
              </motion.div>
            )}

            {/* Completion card */}
            {isDone && (
              <motion.div
                key="done"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="self-center flex flex-col items-center gap-4 py-8"
              >
                <div className="w-14 h-14 bg-[#10b981]/10 border border-[#10b981]/20 rounded-full flex items-center justify-center text-[#10b981]">
                  <CheckCircle2 size={28} />
                </div>
                <div className="text-center">
                  <h3 className="text-lg font-bold">Interrogation Complete</h3>
                  <p className="text-xs text-[#475569] mt-1 font-medium">
                    Product entities, flows, and attack surfaces mapped.
                  </p>
                </div>
                <Button
                  loading={isBlueprintLoading}
                  onClick={handleGenerateBlueprint}
                  icon={Sparkles}
                  className="mt-2"
                >
                  Construct Final Blueprint
                </Button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Input area */}
        {!isDone && (
          <form
            onSubmit={handleSendMessage}
            className="flex items-center gap-3 bg-white/[0.025] border border-white/[0.06] p-2 rounded-2xl backdrop-blur-xl mt-4 shrink-0"
          >
            <div className="flex-grow pl-3">
              <input
                ref={inputRef}
                type="text"
                placeholder={
                  isSending || !conversationId
                    ? 'Engine processing...'
                    : 'Describe your product or answer the questions above...'
                }
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={isSending || isDone || !conversationId}
                className="w-full bg-transparent border-none py-2.5 text-sm font-medium focus:ring-0 placeholder:text-[#334155] outline-none"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSendMessage(e);
                  }
                }}
              />
            </div>
            <Button
              type="submit"
              disabled={!input.trim() || isSending || isDone || !conversationId}
              loading={isSending}
              icon={Send}
              className="!px-5"
            >
              Send
            </Button>
          </form>
        )}
      </div>

      {/* Blueprint generation overlay */}
      <AnimatePresence>
        {isBlueprintLoading && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 backdrop-blur-md"
          >
            <div className="flex flex-col items-center gap-6 p-10 glass-card border-[#8b5cf6]/30 max-w-sm w-full text-center">
              <div className="relative">
                <Loader2 className="animate-spin text-[#8b5cf6]" size={56} />
                <Sparkles
                  className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[#8b5cf6] animate-pulse"
                  size={20}
                />
              </div>
              <div className="flex flex-col gap-2">
                <h3 className="text-xl font-bold tracking-tight">Constructing Blueprint</h3>
                <p className="text-sm text-[#94a3b8]">
                  Synthesizing your product model into a structured attack surface map. Usually takes 30–60 seconds.
                </p>
                {showTimeoutNotice && (
                  <motion.p
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="text-[10px] text-[#f59e0b] font-bold uppercase tracking-widest mt-2"
                  >
                    Taking longer than expected... still working.
                  </motion.p>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Error modal */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-xl p-6"
          >
            <div className="flex flex-col items-center gap-5 p-10 glass-card border-red-500/25 max-w-md w-full text-center">
              <div className="w-14 h-14 bg-red-500/10 border border-red-500/20 rounded-full flex items-center justify-center text-red-400">
                <AlertCircle size={28} />
              </div>
              <div>
                <h3 className="text-lg font-bold">Synthesis Failed</h3>
                <p className="text-sm text-[#94a3b8] mt-2 leading-relaxed">{error}</p>
              </div>
              <div className="flex flex-col w-full gap-3">
                <Button onClick={handleGenerateBlueprint} icon={Sparkles} className="w-full">
                  Re-Attempt Synthesis
                </Button>
                <Button variant="secondary" onClick={() => setError(null)} className="w-full">
                  Back to Interrogation
                </Button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </AppShell>
  );
}
