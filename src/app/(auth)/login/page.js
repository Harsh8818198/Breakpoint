'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mail, Lock, User, ShieldCheck, ChevronRight, AlertCircle } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { clsx } from 'clsx';
import { Button, Input } from '@/components/ui';

export default function LoginPage() {
  const [isLogin, setIsLogin] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const router = useRouter();

  useEffect(() => {
    router.replace('/projects');
  }, [router]);

  const [formData, setFormData] = useState({
    email: '',
    password: '',
    name: '',
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    try {
      const endpoint = isLogin ? '/api/auth/login' : '/api/auth/register';
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });

      const data = await response.json();

      if (!response.ok) {
        const errorMessage = data.error?.message || data.message || 'Authentication failed';
        
        // If it's a validation error, extract the first specific field error
        const details = data.error?.details;
        if (details && typeof details === 'object') {
          // Zod returns an object of arrays for field errors
          const firstFieldKey = Object.keys(details)[0];
          const firstError = details[firstFieldKey];
          if (Array.isArray(firstError) && firstError.length > 0) {
            throw new Error(`${firstError[0]}`);
          }
        }
        
        throw new Error(errorMessage);
      }

      // Successful login/register - Persist token in cookie for middleware and server components
      if (data.data?.token) {
        document.cookie = `token=${data.data.token}; path=/; max-age=${7 * 24 * 60 * 60}; SameSite=Lax`;
      }
      
      router.push('/projects');
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const containerVariants = {
    hidden: { opacity: 0, y: 20 },
    show: {
      opacity: 1,
      y: 0,
      transition: {
        duration: 0.6,
        staggerChildren: 0.1,
      },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, x: -10 },
    show: { opacity: 1, x: 0 },
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      {/* Background Neon Glows */}
      <div className="absolute top-1/4 left-1/4 w-[300px] h-[300px] bg-[#8b5cf6] rounded-full blur-[150px] opacity-[0.05]" />
      <div className="absolute bottom-1/4 right-1/4 w-[300px] h-[300px] bg-[#06b6d4] rounded-full blur-[150px] opacity-[0.05]" />

      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="show"
        className="w-full max-w-md relative z-10"
      >
        <div className="flex flex-col items-center mb-8">
          <motion.div
            initial={{ scale: 0.8, rotate: -10 }}
            animate={{ scale: 1, rotate: 0 }}
            transition={{ type: "spring", stiffness: 260, damping: 20 }}
            className="w-20 h-20 bg-gradient-to-br from-[#8b5cf6] to-[#7c3aed] rounded-3xl flex items-center justify-center shadow-[0_0_40px_rgba(139,92,246,0.3)] mb-4"
          >
            <ShieldCheck className="text-white" size={40} />
          </motion.div>
          <motion.h1 
            variants={itemVariants}
            className="text-4xl font-bold tracking-tighter bg-gradient-to-r from-white to-[#94a3b8] bg-clip-text text-transparent"
          >
            Breakpoint V<span className="text-[#8b5cf6]">2</span>
          </motion.h1>
          <motion.p 
            variants={itemVariants}
            className="text-[#64748b] font-medium mt-1"
          >
            {isLogin ? 'Welcome back, Commander.' : 'Join the Evolutionary Discovery.'}
          </motion.p>
        </div>

        <motion.div
          variants={itemVariants}
          className="glass-card backdrop-blur-2xl border-[rgba(255,255,255,0.08)] shadow-[0_20px_50px_rgba(0,0,0,0.5)] p-8 overflow-hidden relative"
        >
          {/* Progress Line at top */}
          <div className="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-transparent via-[#8b5cf6] to-transparent opacity-50" />

          {/* Tab Switcher */}
          <div className="flex bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.05)] p-1 rounded-xl mb-8 relative">
            <motion.div
              layout
              className="absolute inset-y-1 w-[calc(50%-4px)] bg-white/5 rounded-lg border border-white/5 shadow-inner"
              style={{
                left: isLogin ? '4px' : 'calc(50% + 0px)',
              }}
              transition={{ type: "spring", stroke: 30, damping: 20, mass: 0.8 }}
            />
            <button
              onClick={() => setIsLogin(true)}
              className={clsx(
                'flex-1 py-1.5 text-sm font-semibold transition-colors duration-300 relative z-10',
                isLogin ? 'text-white' : 'text-[#64748b]'
              )}
            >
              Login
            </button>
            <button
              onClick={() => setIsLogin(false)}
              className={clsx(
                'flex-1 py-1.5 text-sm font-semibold transition-colors duration-300 relative z-10',
                !isLogin ? 'text-white' : 'text-[#64748b]'
              )}
            >
              Sign Up
            </button>
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-6">
            <AnimatePresence mode="wait">
              {!isLogin && (
                <motion.div
                  key="name-input"
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.3 }}
                >
                  <Input
                    label="Full Name"
                    placeholder="John Doe"
                    icon={User}
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    required
                  />
                </motion.div>
              )}
            </AnimatePresence>

            <Input
              label="Email Address"
              type="email"
              placeholder="name@company.com"
              icon={Mail}
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              required
            />

            <Input
              label="Password"
              type="password"
              placeholder="••••••••"
              icon={Lock}
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              required
            />

            <AnimatePresence>
              {error && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="bg-[#ef4444]/10 border border-[#ef4444]/20 p-3 rounded-lg flex items-start gap-3"
                >
                  <AlertCircle className="text-[#ef4444] shrink-0 mt-0.5" size={16} />
                  <span className="text-xs text-[#ef4444] font-medium leading-relaxed">{error}</span>
                </motion.div>
              )}
            </AnimatePresence>

            <Button
              type="submit"
              loading={isLoading}
              className="mt-2"
              icon={ChevronRight}
            >
              {isLogin ? 'Access System' : 'Create Account'}
            </Button>
          </form>

          <div className="mt-8 pt-8 border-t border-white/5 text-center">
            <p className="text-sm text-[#475569]">
              {isLogin ? "Don't have an account?" : "Already have an account?"}{' '}
              <button
                onClick={() => setIsLogin(!isLogin)}
                className="text-[#8b5cf6] font-semibold hover:underline"
              >
                {isLogin ? 'Sign up' : 'Login'}
              </button>
            </p>
          </div>
        </motion.div>

        {/* Footer Links */}
        <div className="mt-8 flex items-center justify-center gap-6 text-xs text-[#475569] font-medium uppercase tracking-widest">
          <Link href="/terms" className="hover:text-[#94a3b8] transition-colors">Terms</Link>
          <div className="w-1 h-1 bg-white/10 rounded-full" />
          <Link href="/privacy" className="hover:text-[#94a3b8] transition-colors">Privacy</Link>
          <div className="w-1 h-1 bg-white/10 rounded-full" />
          <Link href="/security" className="hover:text-[#94a3b8] transition-colors">Security</Link>
        </div>
      </motion.div>
    </div>
  );
}
