import React from 'react';
import { Checkbox as ShadCheckbox } from '@/components/ui/checkbox';

export interface CheckboxProps {
    checked: boolean;
    onChange: (checked: boolean) => void;
    label?: React.ReactNode;
    description?: string;
    disabled?: boolean;
    indeterminate?: boolean;
    id?: string;
    className?: string;
}

/**
 * Adapter: preserves upstream xray-editor Checkbox API but renders through the
 * admin panel's shadcn Checkbox (Radix). Indeterminate state goes through
 * Radix's `checked="indeterminate"` value.
 */
export const Checkbox = ({
    checked,
    onChange,
    label,
    description,
    disabled = false,
    indeterminate = false,
    id,
    className = '',
}: CheckboxProps) => {
    const checkboxId =
        id ??
        (typeof label === 'string' ? label.toLowerCase().replace(/\s+/g, '-') : undefined);

    return (
        <label
            htmlFor={checkboxId}
            className={`flex items-start gap-3 cursor-pointer group select-none ${
                disabled ? 'opacity-50 cursor-not-allowed' : ''
            } ${className}`}
        >
            <ShadCheckbox
                id={checkboxId}
                checked={indeterminate ? 'indeterminate' : checked}
                onCheckedChange={(v) => {
                    if (disabled) return;
                    // Radix passes boolean | "indeterminate" — collapse to bool
                    onChange(v === true);
                }}
                disabled={disabled}
                className="mt-0.5 h-[18px] w-[18px] data-[state=checked]:bg-indigo-600 data-[state=checked]:border-indigo-600 border-slate-600 group-hover:border-indigo-500 transition-colors"
            />

            {(label || description) && (
                <div className="flex flex-col gap-0.5">
                    {label && (
                        <span className="text-xs font-bold text-slate-300 group-hover:text-white transition-colors uppercase tracking-wider">
                            {label}
                        </span>
                    )}
                    {description && (
                        <span className="text-[10px] text-slate-500 font-normal normal-case tracking-normal">
                            {description}
                        </span>
                    )}
                </div>
            )}
        </label>
    );
};
