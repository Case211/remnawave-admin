import React from 'react';
import { Icon } from './Icon';

export type BadgeVariant = 'default' | 'primary' | 'success' | 'warning' | 'danger' | 'info';

export interface BadgeProps {
    children: React.ReactNode;
    variant?: BadgeVariant;
    icon?: string;
    onRemove?: () => void;
    onClick?: () => void;
    className?: string;
    size?: 'sm' | 'md';
}

const variantStyles: Record<BadgeVariant, string> = {
    default: 'bg-slate-800 border-slate-700 text-slate-300',
    primary: 'bg-indigo-600/20 border-indigo-500/40 text-indigo-300',
    success: 'bg-emerald-600/20 border-emerald-500/40 text-emerald-300',
    warning: 'bg-amber-500/20 border-amber-500/40 text-amber-300',
    danger: 'bg-rose-600/20 border-rose-500/40 text-rose-300',
    info: 'bg-blue-600/20 border-blue-500/40 text-blue-300',
};

/**
 * Badge — inline status indicator or tag.
 * Use `onRemove` to make it a dismissible chip.
 */
export const Badge = ({
    children,
    variant = 'default',
    icon,
    onRemove,
    onClick,
    className = '',
    size = 'md',
}: BadgeProps) => {
    const sizeClass = size === 'sm' ? 'px-1.5 py-0.5 text-[10px] gap-1' : 'px-2 py-1 text-xs gap-1.5';

    return (
        <span
            onClick={onClick}
            className={`
                inline-flex items-center font-mono rounded border transition-colors
                ${sizeClass}
                ${variantStyles[variant]}
                ${onClick ? 'cursor-pointer hover:brightness-110' : ''}
                ${className}
            `}
        >
            {icon && <Icon name={icon} className="shrink-0" />}
            {children}
            {onRemove && (
                <button
                    onClick={(e) => {
                        e.stopPropagation();
                        onRemove();
                    }}
                    className="hover:text-white transition-colors ml-0.5 shrink-0"
                >
                    <Icon name="X" className="text-[10px]" />
                </button>
            )}
        </span>
    );
};
