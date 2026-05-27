// @ts-nocheck
import React from 'react';
import { Icon } from '../../ui/Icon';

export const BalancerList = ({ balancers, activeIndex, onSelect, onDelete }) => {
    return (
        <div className="flex-1 overflow-y-auto custom-scroll p-2 space-y-1">
            {balancers.map((b, i) => (
                <div key={i} onClick={() => onSelect(i)}
                    className={`p-3 rounded-lg cursor-pointer text-xs flex justify-between items-center group border transition-all mb-1
        ${activeIndex === i ? 'bg-purple-600/20 border-purple-500/50' : 'hover:bg-slate-900 border-transparent'}`}>
                    <div>
                        <div className="flex items-center gap-2">
                            <div className={`font-bold ${activeIndex === i ? 'text-white' : 'text-slate-300'}`}>{b.tag}</div>
                            {/* ИКОНКА ОШИБКИ */}
                            {(!b.selector || b.selector.length === 0) && (
                                <Icon name="Warning" className="text-rose-500 animate-bounce" weight="fill" title="Empty selector!" />
                            )}
                        </div>
                        <div className="text-[10px] text-slate-500 mt-0.5">Strategy: {b.strategy?.type || 'random'}</div>
                    </div>
                    {/* Кнопка удаления */}
                    <button 
                        onClick={(e) => { e.stopPropagation(); onDelete(i); }}
                        className="md:opacity-0 md:group-hover:opacity-100 p-1.5 hover:bg-rose-900/50 rounded-md text-slate-500 hover:text-rose-400 transition-all"
                    >
                        <Icon name="Trash" className="text-xs" />
                    </button>
                </div>
            ))}
        </div>
    );
};