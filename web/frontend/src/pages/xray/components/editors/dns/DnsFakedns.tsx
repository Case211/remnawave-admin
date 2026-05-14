// @ts-nocheck
import React from 'react';
import { Button } from '../../ui/Button';
import { Icon } from '../../ui/Icon';

export const DnsFakedns = ({ fakedns = [], onChange }) => {
    // fakedns - это массив объектов { ipPool, poolSize }

    const addPool = () => {
        onChange([...fakedns, { ipPool: "198.18.0.0/15", poolSize: 65535 }]);
    };

    const removePool = (idx) => {
        const n = [...fakedns];
        n.splice(idx, 1);
        onChange(n);
    };

    const updatePool = (idx, field, val) => {
        const n = [...fakedns];
        n[idx] = { ...n[idx], [field]: val };
        onChange(n);
    };

    return (
        <div className="h-full flex flex-col">
            <div className="flex justify-between items-center mb-4">
                <div>
                    <label className="label-xs">FakeDNS Pools</label>
                    <p className="text-[10px] text-slate-500">Virtual IP ranges for domains</p>
                </div>
                <Button variant="ghost" className="px-2 py-1 text-xs" onClick={addPool} icon="Plus">Add Pool</Button>
            </div>
            
            <div className="flex-1 overflow-y-auto custom-scroll space-y-3 pr-1">
                {fakedns.map((item, i) => (
                    <div key={i} className="bg-slate-900 p-3 rounded-lg border border-slate-800 flex gap-4 items-end">
                        <div className="flex-1">
                            <label className="label-xs mb-1">IP Pool (CIDR)</label>
                            <input className="input-base font-mono text-xs" 
                                value={item.ipPool} 
                                onChange={e => updatePool(i, 'ipPool', e.target.value)}
                                placeholder="198.18.0.0/15"
                            />
                        </div>
                        <div className="w-1/3">
                            <label className="label-xs mb-1">Size</label>
                            <input type="number" className="input-base font-mono text-xs" 
                                value={item.poolSize} 
                                onChange={e => updatePool(i, 'poolSize', parseInt(e.target.value))}
                            />
                        </div>
                        <button onClick={() => removePool(i)} className="p-2.5 bg-slate-800 hover:bg-rose-600 rounded text-slate-400 hover:text-white transition-colors">
                            <Icon name="Trash" />
                        </button>
                    </div>
                ))}
                {fakedns.length === 0 && (
                    <div className="text-center py-10 bg-slate-900/30 rounded-xl border border-dashed border-slate-800">
                        <p className="text-xs text-slate-500">No FakeDNS pools configured.</p>
                        <p className="text-[10px] text-slate-600 mt-1">Add one if you use TProxy or want to hide DNS results.</p>
                    </div>
                )}
            </div>
        </div>
    );
};