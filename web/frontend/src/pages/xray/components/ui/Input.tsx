import React from 'react';
import { Icon } from './Icon';

export interface InputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'size'> {
    /** Icon name (phosphor) shown on the left */
    leftIcon?: string;
    /** Icon name (phosphor) shown on the right */
    rightIcon?: string;
    /** Error message — turns border red */
    error?: string;
    /** Soft label above the field */
    label?: string;
    /** Helper text below the field */
    hint?: string;
    size?: 'sm' | 'md' | 'lg';
}

const sizeClasses = {
    sm: 'text-xs py-1.5 px-2.5',
    md: 'text-sm py-2 px-3',
    lg: 'text-base py-2.5 px-4',
};

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
    ({ leftIcon, rightIcon, error, label, hint, size = 'md', className = '', id, ...rest }, ref) => {
        const inputId = id ?? label?.toLowerCase().replace(/\s+/g, '-');
        const border = error
            ? 'border-rose-500/70 focus:border-rose-500 focus:ring-rose-500/30'
            : 'border-slate-700 focus:border-indigo-500 focus:ring-indigo-500/30';

        return (
            <div className="flex flex-col gap-1.5">
                {label && (
                    <label
                        htmlFor={inputId}
                        className="text-[10px] uppercase text-slate-500 font-bold tracking-widest"
                    >
                        {label}
                    </label>
                )}
                <div className="relative">
                    {leftIcon && (
                        <Icon
                            name={leftIcon}
                            className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none"
                        />
                    )}
                    <input
                        ref={ref}
                        id={inputId}
                        className={`
                            w-full bg-slate-950 border rounded-lg outline-none
                            text-white placeholder:text-slate-600
                            focus:ring-1 transition-all
                            ${sizeClasses[size]}
                            ${leftIcon ? 'pl-9' : ''}
                            ${rightIcon ? 'pr-9' : ''}
                            ${border}
                            ${className}
                        `}
                        {...rest}
                    />
                    {rightIcon && (
                        <Icon
                            name={rightIcon}
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none"
                        />
                    )}
                </div>
                {error && (
                    <span className="text-[10px] text-rose-500 font-bold animate-in fade-in slide-in-from-right-1">
                        {error}
                    </span>
                )}
                {hint && !error && (
                    <span className="text-[10px] text-slate-600">{hint}</span>
                )}
            </div>
        );
    },
);

Input.displayName = 'Input';
