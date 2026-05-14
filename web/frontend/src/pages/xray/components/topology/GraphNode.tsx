// @ts-nocheck
import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { Icon } from '../ui/Icon';

const colors = {
    inbound: "border-emerald-500/50 bg-emerald-900/20 text-emerald-100",
    outbound: "border-blue-500/50 bg-blue-900/20 text-blue-100",
    rule: "border-slate-500/50 bg-slate-800 text-slate-200",
    balancer: "border-purple-500/50 bg-purple-900/20 text-purple-100",
    default: "border-slate-700 bg-slate-900 text-slate-400"
};

const icons = {
    inbound: "ArrowCircleDown",
    outbound: "PaperPlaneRight",
    rule: "ArrowsSplit",
    balancer: "Scales",
    default: "Question"
};

export const GraphNode = memo(({ data }: any) => {
    const type = data.type || 'default';
    const style = colors[type] || colors.default;
    const iconName = icons[type] || icons.default;

    return (
        // Добавил mx-auto для центрирования, если нужно
        <div className={`px-4 py-3 rounded-xl border shadow-xl min-w-[200px] backdrop-blur-sm transition-all hover:scale-105 hover:shadow-2xl ${style}`}>
            
            {/* Входы (Сверху) */}
            {type !== 'inbound' && (
                <Handle 
                    type="target" 
                    position={Position.Top} 
                    className="!bg-slate-400 !w-3 !h-3 !-top-1.5 rounded-full border border-slate-900" 
                />
            )}
            
            <div className="flex items-center gap-3 justify-center text-center">
                <div className="p-2 rounded-lg bg-black/20 shrink-0">
                    <Icon name={iconName} className="text-xl" />
                </div>
                <div className="overflow-hidden">
                    <div className="text-[9px] uppercase opacity-60 font-bold tracking-widest mb-0.5">{data.labelType}</div>
                    <div className="text-sm font-bold font-mono truncate max-w-[140px]" title={data.label}>
                        {data.label}
                    </div>
                    {data.details && (
                        <div className="text-[10px] opacity-70 mt-1 font-mono bg-black/10 px-1.5 py-0.5 rounded inline-block truncate max-w-full">
                            {data.details}
                        </div>
                    )}
                </div>
            </div>

            {/* Выходы (Снизу) */}
            {type !== 'outbound' && (
                <Handle 
                    type="source" 
                    position={Position.Bottom} 
                    className="!bg-slate-400 !w-3 !h-3 !-bottom-1.5 rounded-full border border-slate-900" 
                />
            )}
        </div>
    );
});