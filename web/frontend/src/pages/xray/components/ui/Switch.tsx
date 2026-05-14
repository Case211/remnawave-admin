import { Switch as ShadSwitch } from '@/components/ui/switch';

interface SwitchProps {
    checked: boolean;
    onChange: (checked: boolean) => void;
    label?: string;
    disabled?: boolean;
}

/**
 * Adapter: keeps the upstream xray-editor Switch API (checked / onChange / label),
 * but renders our shadcn Switch (Radix) underneath. The label is composed
 * locally because the upstream component bundles it inside <label>.
 */
export const Switch = ({ checked, onChange, label, disabled = false }: SwitchProps) => {
    return (
        <label
            className={`flex items-center gap-3 cursor-pointer group ${
                disabled ? 'opacity-50 cursor-not-allowed' : ''
            }`}
        >
            <ShadSwitch
                checked={checked}
                onCheckedChange={onChange}
                disabled={disabled}
                className="h-5 w-10 data-[state=checked]:bg-indigo-600 data-[state=unchecked]:bg-slate-700 border-0 [&>span]:h-3 [&>span]:w-3 [&>span]:data-[state=checked]:translate-x-5 [&>span]:data-[state=unchecked]:translate-x-1"
            />
            {label && (
                <span className="text-xs font-bold text-slate-400 uppercase tracking-wider group-hover:text-slate-200 transition-colors">
                    {label}
                </span>
            )}
        </label>
    );
};
