import React from 'react';
import { Icon } from './Icon';

export type AlertVariant = 'info' | 'warning' | 'error' | 'success';

export interface AlertProps {
    variant?: AlertVariant;
    title?: string;
    children: React.ReactNode;
    onDismiss?: () => void;
    className?: string;
    icon?: string;
}

const variantConfig: Record<AlertVariant, { bg: string; border: string; text: string; icon: string }> = {
    info: {
        bg: 'bg-blue-900/20',
        border: 'border-blue-500/40',
        text: 'text-blue-300',
        icon: 'Info',
    },
    warning: {
        bg: 'bg-amber-900/20',
        border: 'border-amber-500/40',
        text: 'text-amber-300',
        icon: 'Warning',
    },
    error: {
        bg: 'bg-rose-900/20',
        border: 'border-rose-500/50',
        text: 'text-rose-300',
        icon: 'WarningCircle',
    },
    success: {
        bg: 'bg-emerald-900/20',
        border: 'border-emerald-500/40',
        text: 'text-emerald-300',
        icon: 'CheckCircle',
    },
};

export const Alert = ({ variant = 'info', title, children, onDismiss, className = '', icon }: AlertProps) => {
    const cfg = variantConfig[variant];

    return (
        <div
            className={`
                flex gap-3 p-3 rounded-xl border text-sm animate-in fade-in slide-in-from-top-2
                ${cfg.bg} ${cfg.border} ${cfg.text} ${className}
            `}
        >
            <Icon name={icon ?? cfg.icon} weight="fill" className="mt-0.5 shrink-0" />
            <div className="flex-1 min-w-0">
                {title && <p className="font-bold mb-0.5">{title}</p>}
                <div className="opacity-90 text-xs leading-relaxed">{children}</div>
            </div>
            {onDismiss && (
                <button
                    onClick={onDismiss}
                    className="shrink-0 p-0.5 hover:opacity-70 transition-opacity"
                >
                    <Icon name="X" />
                </button>
            )}
        </div>
    );
};
