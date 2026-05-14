export interface DividerProps {
    label?: string;
    className?: string;
    orientation?: 'horizontal' | 'vertical';
}

export const Divider = ({ label, className = '', orientation = 'horizontal' }: DividerProps) => {
    if (orientation === 'vertical') {
        return <div className={`w-px bg-slate-800 self-stretch mx-1 ${className}`} />;
    }

    if (label) {
        return (
            <div className={`flex items-center gap-3 my-2 ${className}`}>
                <div className="flex-1 h-px bg-slate-800" />
                <span className="text-[10px] uppercase font-bold text-slate-600 tracking-widest whitespace-nowrap">
                    {label}
                </span>
                <div className="flex-1 h-px bg-slate-800" />
            </div>
        );
    }

    return <div className={`h-px bg-slate-800 my-2 ${className}`} />;
};
