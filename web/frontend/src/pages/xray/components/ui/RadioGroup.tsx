// @ts-nocheck
import React from 'react';

export interface RadioOption<T extends string = string> {
    value: T;
    label: string;
    description?: string;
    disabled?: boolean;
}

export interface RadioGroupProps<T extends string = string> {
    value: T;
    onChange: (value: T) => void;
    options: RadioOption<T>[];
    label?: string;
    direction?: 'horizontal' | 'vertical';
    className?: string;
    /** Renders as pill buttons instead of classic radio circles */
    variant?: 'radio' | 'pills';
}

export function RadioGroup<T extends string = string>({
    value,
    onChange,
    options,
    label,
    direction = 'vertical',
    className = '',
    variant = 'radio',
}: RadioGroupProps<T>) {
    if (variant === 'pills') {
        return (
            <div className={`flex flex-col gap-1.5 ${className}`}>
                {label && (
                    <span className="text-[10px] uppercase text-slate-500 font-bold tracking-widest">{label}</span>
                )}
                <div className={`flex gap-1.5 flex-wrap ${direction === 'horizontal' ? '' : 'flex-col'}`}>
                    {options.map((opt) => (
                        <button
                            key={opt.value}
                            type="button"
                            disabled={opt.disabled}
                            onClick={() => onChange(opt.value)}
                            className={`
                                px-3 py-1.5 rounded-lg text-xs font-bold border transition-all
                                disabled:opacity-50 disabled:cursor-not-allowed
                                ${value === opt.value
                                    ? 'bg-indigo-600 border-indigo-500 text-white shadow-md shadow-indigo-500/20'
                                    : 'bg-slate-900 border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200'}
                            `}
                        >
                            {opt.label}
                        </button>
                    ))}
                </div>
            </div>
        );
    }

    return (
        <div className={`flex flex-col gap-1.5 ${className}`}>
            {label && (
                <span className="text-[10px] uppercase text-slate-500 font-bold tracking-widest">{label}</span>
            )}
            <div className={`flex gap-3 ${direction === 'vertical' ? 'flex-col' : 'flex-row flex-wrap'}`}>
                {options.map((opt) => (
                    <label
                        key={opt.value}
                        className={`flex items-start gap-2.5 cursor-pointer group ${opt.disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                        <div className="relative mt-0.5 shrink-0">
                            <input
                                type="radio"
                                name={label}
                                value={opt.value}
                                checked={value === opt.value}
                                disabled={opt.disabled}
                                onChange={() => !opt.disabled && onChange(opt.value)}
                                className="sr-only"
                            />
                            <div
                                className={`
                                    w-4 h-4 rounded-full border-2 flex items-center justify-center transition-all
                                    ${value === opt.value
                                        ? 'border-indigo-500 bg-indigo-600'
                                        : 'border-slate-600 bg-slate-900 group-hover:border-indigo-500'}
                                `}
                            >
                                {value === opt.value && (
                                    <div className="w-1.5 h-1.5 rounded-full bg-white" />
                                )}
                            </div>
                        </div>
                        <div className="flex flex-col gap-0.5">
                            <span className="text-xs font-bold text-slate-300 group-hover:text-white transition-colors uppercase tracking-wider">
                                {opt.label}
                            </span>
                            {opt.description && (
                                <span className="text-[10px] text-slate-500 font-normal normal-case tracking-normal">
                                    {opt.description}
                                </span>
                            )}
                        </div>
                    </label>
                ))}
            </div>
        </div>
    );
}
