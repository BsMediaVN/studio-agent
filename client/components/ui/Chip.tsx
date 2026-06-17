import type { HTMLAttributes, ReactNode } from 'react';

export type ChipVariant = 'default' | 'warn' | 'playing' | 'connecting' | 'error' | 'completed';

interface ChipProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: ChipVariant;
  dot?: boolean;
  children: ReactNode;
}

const variantClass: Record<ChipVariant, string> = {
  default: 'status-chip',
  warn: 'status-chip chip-warn',
  playing: 'status-chip status-playing',
  connecting: 'status-chip status-connecting',
  error: 'status-chip status-error',
  completed: 'status-chip status-completed',
};

export function Chip({ variant = 'default', dot = false, className = '', children, ...rest }: ChipProps) {
  return (
    <span className={`${variantClass[variant]} ${className}`} {...rest}>
      {dot && <span className="status-dot" />}
      {children}
    </span>
  );
}
