import React from 'react';

export interface NumberInputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type' | 'onChange' | 'value'> {
    value: number | string;
    onChange: (value: number) => void;
    label?: string;
    error?: string;
    hint?: string;
    min?: number;
    max?: number;
    step?: number;
    suffix?: string;
}

export const NumberInput = React.forwardRef<HTMLInputElement, NumberInputProps>(
    ({ value, onChange, label, error, hint, min, max, step = 1, suffix, className = '', id, ...rest }, ref) => {
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
                    <input
                        ref={ref}
                        id={inputId}
                        type="number"
                        value={value}
                        min={min}
                        max={max}
                        step={step}
                        onChange={(e) => onChange(Number(e.target.value))}
                        className={`
                            w-full bg-slate-950 border rounded-lg outline-none
                            text-white py-2 text-sm font-mono
                            focus:ring-1 transition-all
                            ${suffix ? 'pl-3 pr-12' : 'px-3'}
                            ${border}
                            ${className}
                        `}
                        {...rest}
                    />
                    {suffix && (
                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 text-xs font-mono pointer-events-none">
                            {suffix}
                        </span>
                    )}
                </div>
                {error && (
                    <span className="text-[10px] text-rose-500 font-bold animate-in fade-in">
                        {error}
                    </span>
                )}
                {hint && !error && <span className="text-[10px] text-slate-600">{hint}</span>}
            </div>
        );
    },
);

NumberInput.displayName = 'NumberInput';
