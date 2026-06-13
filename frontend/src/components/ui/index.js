'use client';
import { clsx } from 'clsx';
import { Loader2 } from 'lucide-react';

export function Button({ 
  children, 
  className, 
  variant = 'primary', 
  loading = false, 
  icon: Icon,
  ...props 
}) {
  const variants = {
    primary: 'bg-gradient-to-br from-[#8b5cf6] to-[#7c3aed] text-white shadow-[0_0_20px_rgba(139,92,246,0.2)] hover:shadow-[0_0_30px_rgba(139,92,246,0.3)]',
    secondary: 'bg-[rgba(255,255,255,0.05)] border border-[rgba(255,255,255,0.1)] text-[#94a3b8] hover:bg-[rgba(255,255,255,0.1)] hover:text-white',
    ghost: 'hover:bg-[rgba(255,255,255,0.05)] text-[#64748b] hover:text-[#94a3b8]',
    outline: 'border border-[#8b5cf6] text-[#8b5cf6] hover:bg-[#8b5cf6] hover:text-white',
    critical: 'bg-[#ef4444] text-white shadow-[0_0_20px_rgba(239,68,68,0.2)] hover:bg-[#dc2626]',
  };

  return (
    <button
      disabled={loading || props.disabled}
      className={clsx(
        'relative inline-flex items-center justify-center px-6 py-2.5 rounded-xl font-semibold transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed group overflow-hidden',
        variants[variant],
        className
      )}
      {...props}
    >
      <span className={clsx('flex items-center gap-2 transition-opacity', loading ? 'opacity-0' : 'opacity-100')}>
        {Icon && <Icon size={18} className="group-hover:scale-110 transition-transform" />}
        {children}
      </span>
      
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center">
          <Loader2 className="animate-spin text-white" size={20} />
        </div>
      )}

      {/* Glossy overlay on hover */}
      <div className="absolute inset-x-0 -top-px h-px bg-white/20 transition-opacity opacity-0 group-hover:opacity-100" />
    </button>
  );
}

export function Input({ label, error, className, icon: Icon, ...props }) {
  return (
    <div className={clsx('flex flex-col gap-1.5 w-full', className)}>
      {label && <label className="text-sm font-medium text-[#94a3b8] px-1">{label}</label>}
      <div className="relative group">
        {Icon && (
          <div className="absolute left-4 top-1/2 -translate-y-1/2 text-[#64748b] group-focus-within:text-[#8b5cf6] transition-colors">
            <Icon size={18} />
          </div>
        )}
        <input
          className={clsx(
            'w-full bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.08)] rounded-xl py-2.5 transition-all text-white placeholder:text-[#475569] focus:outline-none focus:ring-1 focus:ring-[#8b5cf6] focus:border-[#8b5cf6] focus:bg-[rgba(255,255,255,0.05)]',
            Icon ? 'pl-11 pr-4' : 'px-4',
            error ? 'border-[#ef4444] animate-shake' : ''
          )}
          {...props}
        />
      </div>
      {error && <span className="text-xs text-[#ef4444] px-1 font-medium">{error}</span>}
    </div>
  );
}
