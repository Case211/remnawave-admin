import React from 'react';
import { Help } from './Help';

interface FormFieldProps {
    label: string;
    help?: string;
    error?: string;
    children: React.ReactNode;
    className?: string;
    horizontal?: boolean;
}

export const FormField = ({ label, help, error, children, className = "", horizontal = false }: FormFieldProps) => {
    if (horizontal) {
        return (
            <div className={`flex items-center justify-between gap-4 py-1 ${className}`}>
                <div className="flex items-center gap-2">
                    <label className="text-xs text-slate-400 font-bold uppercase tracking-wider cursor-pointer">
                        {label}
                    </label>
                    {help && <Help>{help}</Help>}
                </div>
                <div className="flex flex-col items-end">
                    {children}
                    {error && <span className="text-[10px] text-rose-500 mt-1 font-medium">{error}</span>}
                </div>
            </div>
        );
    }

    return (
        <div className={`flex flex-col gap-1.5 ${className}`}>
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <label className="text-[10px] uppercase text-slate-500 font-bold tracking-widest">
                        {label}
                    </label>
                    {help && <Help>{help}</Help>}
                </div>
                {error && <span className="text-[10px] text-rose-500 font-bold animate-in fade-in slide-in-from-right-1">{error}</span>}
            </div>
            <div className="relative">
                {children}
            </div>
        </div>
    );
};
