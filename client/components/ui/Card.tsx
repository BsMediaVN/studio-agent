import type { HTMLAttributes, ReactNode } from 'react';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'panel' | 'surface';
  children: ReactNode;
}

export function Card({ variant = 'panel', className = '', children, ...rest }: CardProps) {
  const base = variant === 'surface' ? 'surface-card' : 'panel-card';
  return (
    <div className={`${base} ${className}`} {...rest}>
      {children}
    </div>
  );
}
