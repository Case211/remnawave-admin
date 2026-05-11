import React from 'react';

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
    label?: string;
    error?: string;
    hint?: string;
    monospace?: boolean;
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
    ({ label, error, hint, monospace = false, className = '', id, ...rest }, ref) => {
        const textareaId = id ?? label?.toLowerCase().replace(/\s+/g, '-');
        const border = error
            ? 'border-rose-500/70 focus:border-rose-500 focus:ring-rose-500/30'
            : 'border-slate-700 focus:border-indigo-500 focus:ring-indigo-500/30';

        return (
            <div className="flex flex-col gap-1.5">
                {label && (
                    <label
                        htmlFor={textareaId}
                        className="text-[10px] uppercase text-slate-500 font-bold tracking-widest"
                    >
                        {label}
                    </label>
                )}
                <textarea
                    ref={ref}
                    id={textareaId}
                    className={`
                        w-full bg-slate-950 border rounded-lg outline-none resize-y min-h-[80px]
                        text-white placeholder:text-slate-600 text-sm py-2 px-3
                        focus:ring-1 transition-all custom-scroll
                        ${monospace ? 'font-mono text-xs' : ''}
                        ${border}
                        ${className}
                    `}
                    {...rest}
                />
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

Textarea.displayName = 'Textarea';
