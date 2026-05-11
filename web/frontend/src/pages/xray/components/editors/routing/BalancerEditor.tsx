// @ts-nocheck
import React, { useState } from 'react';
import { Icon } from '../../ui/Icon';
import { JsonField } from '../../ui/JsonField';
import { validateBalancer } from '../../../utils/validator';
import { Select } from '../../ui/Select';

export const BalancerEditor = ({ balancer, onChange, outboundTags, rawMode }: any) => {
    // Локальный стейт для инпута, чтобы делать подсветку "на лету"
    const [inputValue, setInputValue] = useState("");

    if (!balancer) {
        return (
            <div className="flex-1 flex flex-col items-center justify-center text-slate-600 h-full">
                <Icon name="Scales" className="text-6xl mb-4 opacity-10" />
                <p>Select a balancer to configure</p>
            </div>
        );
    }

    if (rawMode) {
        return (
            <div className="flex-1 w-full h-full p-4 bg-slate-950">
                <JsonField label="Raw Balancer JSON" value={balancer} onChange={onChange} schemaMode="balancer" className="h-full"/>
            </div>
        );
    }

    const currentSelector = balancer.selector || [];
    
    const errors = validateBalancer(balancer);
    const selectorError = errors.find(e => e.field === 'selector');
    const tagError = errors.find(e => e.field === 'tag');

    const update = (field: string | null, val: any) => {
        if (field === null) {
            onChange(null);
        } else {
            onChange({ ...balancer, [field]: val });
        }
    };

    // Добавление/Удаление тега по клику
    const toggleSelector = (tag: string) => {
        // Если тег уже есть в списке (точное совпадение) - удаляем
        if (currentSelector.includes(tag)) {
            update('selector', currentSelector.filter((s: string) => s !== tag));
        } else {
            // Иначе добавляем
            update('selector', [...currentSelector, tag]);
        }
    };

    // Логика проверки совпадений
    const checkMatch = (tag: string) => {
        const exact = currentSelector.includes(tag);
        const prefixMatch = !exact && currentSelector.some((s: string) => tag.startsWith(s));
        const pendingMatch = inputValue && tag.startsWith(inputValue) && !exact && !prefixMatch;

        return { exact, prefixMatch, pendingMatch };
    };

    const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter') {
            const val = e.currentTarget.value.trim();

            if (val && !currentSelector.includes(val)) {
                update('selector', [...currentSelector, val]);
                setInputValue("");
            }
        }
    };

    return (
        <div className="flex-1 w-full overflow-y-auto custom-scroll p-6 space-y-6 bg-slate-950/30 h-full">
            
            <div className="flex justify-end mb-4">
                 <button onClick={() => {
                     if (confirm("Delete this balancer?")) {
                         // Простой способ удаления: меняем тег на пустой или вызываем спец. экшен, 
                         // но в данном случае достаточно сбросить balancer в null
                         onChange(null);
                     }
                 }} className="text-xs text-rose-500 hover:text-rose-400 font-bold flex items-center gap-1 bg-rose-950/20 px-3 py-1.5 rounded-lg border border-rose-900/50 hover:bg-rose-900/30">
                     <Icon name="Trash" /> Delete Balancer
                 </button>
            </div>

            {selectorError && (
                <div className="p-4 rounded-xl bg-rose-900/20 border border-rose-500/50 text-rose-200 flex gap-3 items-start animate-pulse">
                    <Icon name="WarningOctagon" className="mt-1 shrink-0 text-xl" weight="fill" />
                    <div>
                        <strong className="block text-sm">Critical Config Error</strong>
                        <p className="text-xs opacity-80">{selectorError.message}</p>
                    </div>
                </div>
            )}

            <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                    <label className="label-xs">Balancer Tag</label>
                    <input 
                        className={`input-base font-bold font-mono ${tagError ? 'border-rose-500 bg-rose-500/10' : ''}`} 
                        value={balancer.tag || ""} 
                        onChange={e => update('tag', e.target.value)} 
                    />
                    {tagError && <span className="text-[10px] text-rose-500">{tagError.message}</span>}
                </div>
                
                    <Select 
                        label="Strategy"
                        value={balancer.strategy?.type || "random"} 
                        onChange={val => update('strategy', { ...balancer.strategy, type: val })}
                        options={[
                            { value: "random", label: "Random", description: "Standard load balancing" },
                            { value: "roundRobin", label: "Round Robin", description: "Sequential selection" },
                            { value: "leastPing", label: "Least Ping", description: "Best latency (Requires Observatory)" },
                            { value: "leastLoad", label: "Least Load", description: "Least active connections" },
                        ]}
                    />

                    <Select 
                        label="Fallback Tag (Optional)"
                        value={balancer.fallbackTag || ""} 
                        onChange={val => {
                            if (val === "") {
                                const newB = { ...balancer };
                                delete newB.fallbackTag;
                                onChange(newB);
                            } else {
                                update('fallbackTag', val);
                            }
                        }}
                        options={[
                            { value: "", label: "Нет" },
                            ...outboundTags.map((tag: string) => ({ value: tag, label: tag }))
                        ]}
                    />
            </div>

            <div className={`bg-slate-900/50 p-4 rounded-xl border ${selectorError ? 'border-rose-500/50' : 'border-slate-800/50'}`}>
                <div className="flex justify-between items-end mb-4">
                    <div>
                        <label className={`label-xs block ${selectorError ? 'text-rose-400' : ''}`}>Target Outbounds</label>
                        <span className="text-[10px] text-slate-500">
                            Purple = Active. <span className="text-amber-400">Amber = Preview (Matches current input)</span>.
                        </span>
                    </div>
                </div>
                
                <div className="grid grid-cols-2 lg:grid-cols-3 gap-2 max-h-[300px] overflow-y-auto custom-scroll">
                    {outboundTags.map((tag: string) => {
                        const { exact, prefixMatch, pendingMatch } = checkMatch(tag);
                        
                        // Определяем стиль на основе состояния
                        let styleClass = 'bg-slate-950 border-slate-700 text-slate-400'; // Default
                        
                        if (exact) {
                            styleClass = 'bg-purple-600 border-purple-500 text-white';
                        } else if (prefixMatch) {
                            styleClass = 'bg-purple-900/40 border-purple-500/60 text-purple-200';
                        } else if (pendingMatch) {
                            // Стиль для предпросмотра (то, что мы сейчас печатаем)
                            styleClass = 'bg-amber-900/30 border-amber-500 text-amber-200 animate-pulse';
                        }

                        return (
                            <div key={tag} onClick={() => toggleSelector(tag)} 
                                className={`cursor-pointer px-3 py-2 rounded-lg border text-xs font-mono flex justify-between items-center transition-all select-none ${styleClass}`}
                            >
                                <span className="truncate">{tag}</span>
                                {exact && <Icon name="CheckCircle" className="text-white shrink-0 ml-2"/>}
                                {prefixMatch && <Icon name="GitMerge" className="text-purple-400 shrink-0 ml-2" />}
                                {pendingMatch && <Icon name="Eye" className="text-amber-400 shrink-0 ml-2" />}
                            </div>
                        )
                    })}
                </div>
                
                <div className="mt-4 pt-4 border-t border-slate-800">
                    <label className="label-xs">Add Prefix / Selector</label>
                    <div className="flex gap-2 items-center">
                        <input className="flex-1 input-base text-xs font-mono" 
                            placeholder="e.g. 'NEO' (will highlight matches above)" 
                            value={inputValue}
                            onChange={e => setInputValue(e.target.value)}
                            onKeyDown={handleInputKeyDown}
                        />
                        {inputValue && (
                             <button onClick={() => {
                                 // Кнопка быстрого добавления того, что ввели
                                 if (!currentSelector.includes(inputValue)) {
                                     update('selector', [...currentSelector, inputValue]);
                                     setInputValue("");
                                 }
                             }} className="p-2 bg-indigo-600 rounded text-white text-xs font-bold hover:bg-indigo-500">
                                 Add
                             </button>
                        )}
                    </div>
                    
                    {/* Список активных селекторов (Теги внизу) */}
                    <div className="flex flex-wrap gap-2 mt-2">
                        {currentSelector.map((sel: string) => (
                            <span key={sel} className="text-[10px] px-2 py-1 rounded border flex items-center gap-1 bg-purple-900/50 border-purple-800 text-purple-300">
                                {sel}
                                <button onClick={() => update('selector', currentSelector.filter((s: string) => s !== sel))} className="hover:text-white ml-1">×</button>
                            </span>
                        ))}
                    </div>
                </div>
            </div>
            
            {(balancer.strategy?.type === 'leastPing' || balancer.strategy?.type === 'leastLoad') && (
                <div className="p-3 rounded-lg bg-yellow-900/20 border border-yellow-700/50 text-xs text-yellow-200 flex gap-2 items-start">
                    <Icon name="Warning" className="mt-0.5 shrink-0" weight="fill" />
                    <div>
                        <strong>Observatory Required:</strong> For "{balancer.strategy.type}" to work, you must configure <b>Observatory</b> in Settings.
                    </div>
                </div>
            )}

            {balancer.strategy?.type === 'leastLoad' && (
                <div className="bg-slate-900/50 p-4 rounded-xl border border-slate-800/50 space-y-4">
                    <h4 className="text-xs font-bold text-slate-400">LeastLoad Settings</h4>
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="label-xs">Expected Nodes</label>
                            <input className="input-base font-mono" type="number" placeholder="2" 
                                value={balancer.strategy?.settings?.expected || ""} 
                                onChange={e => update('strategy', { ...balancer.strategy, settings: { ...balancer.strategy?.settings, expected: Number(e.target.value) } })} />
                        </div>
                        <div>
                            <label className="label-xs">Max RTT</label>
                            <input className="input-base font-mono" placeholder="1s" 
                                value={balancer.strategy?.settings?.maxRTT || ""} 
                                onChange={e => update('strategy', { ...balancer.strategy, settings: { ...balancer.strategy?.settings, maxRTT: e.target.value } })} />
                        </div>
                        <div>
                            <label className="label-xs">Tolerance</label>
                            <input className="input-base font-mono" type="number" step="0.01" placeholder="0.01" 
                                value={balancer.strategy?.settings?.tolerance || ""} 
                                onChange={e => update('strategy', { ...balancer.strategy, settings: { ...balancer.strategy?.settings, tolerance: Number(e.target.value) } })} />
                        </div>
                        <div>
                            <label className="label-xs">Baselines (CSV)</label>
                            <input className="input-base font-mono" placeholder="1s, 2s" 
                                value={(balancer.strategy?.settings?.baselines || []).join(', ')} 
                                onChange={e => update('strategy', { ...balancer.strategy, settings: { ...balancer.strategy?.settings, baselines: e.target.value.split(',').map((s: string) => s.trim()).filter((s: string) => s) } })} />
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};