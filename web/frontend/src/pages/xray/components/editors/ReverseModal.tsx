// @ts-nocheck
import React from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Icon } from '../ui/Icon';
import { useReverseEditor } from '../../hooks/useReverseEditor';

export const ReverseModal = ({ onClose }: any) => {
    const {
        reverse,
        activeTab,
        setActiveTab,
        addItem,
        removeItem,
        updateItem
    } = useReverseEditor();

    const renderList = (type: 'bridges' | 'portals') => (
        <div className="space-y-4">
            {(reverse[type] || []).map((item: any, i: number) => (
                <div key={i} className="bg-slate-900 border border-slate-800 p-5 rounded-2xl flex flex-col md:flex-row items-end gap-4 relative group shadow-lg">
                    <div className="flex-1 w-full">
                        <label className="label-xs text-indigo-400">Tag</label>
                        <input className="input-base" 
                            placeholder="e.g. reverse-tag"
                            value={item.tag} 
                            onChange={e => updateItem(type, i, 'tag', e.target.value)}
                        />
                    </div>
                    <div className="flex-1 w-full">
                        <label className="label-xs text-indigo-400">Domain</label>
                        <input className="input-base font-mono" 
                            placeholder="e.g. portal.example.com"
                            value={item.domain} 
                            onChange={e => updateItem(type, i, 'domain', e.target.value)}
                        />
                    </div>
                    <button 
                        onClick={() => removeItem(type, i)} 
                        className="bg-rose-500/10 border border-rose-500/20 p-2.5 rounded-xl text-rose-500 hover:bg-rose-500 hover:text-white transition-all shadow-sm"
                        title="Удалить"
                    >
                        <Icon name="Trash" weight="bold" />
                    </button>
                </div>
            ))}
            {(reverse[type] || []).length === 0 && (
                <div className="text-center py-16 bg-slate-950/50 border border-dashed border-slate-800 rounded-2xl text-slate-500 text-sm">
                    <Icon name="ArrowsLeftRight" className="text-3xl mx-auto mb-3 opacity-20" />
                    No {type} configured yet.
                </div>
            )}
            <Button variant="secondary" className="w-full h-12 rounded-xl border-dashed border-2 border-slate-800 hover:border-indigo-500/50" onClick={() => addItem(type)} icon="Plus">
                Add New {type === 'bridges' ? 'Bridge' : 'Portal'}
            </Button>
        </div>
    );

    return (
        <Modal 
            title="Reverse-прокси" 
            onClose={onClose} 
            onSave={() => onClose()}
            className="md:max-w-[800px]"
            extraButtons={
                <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800">
                    <button onClick={() => setActiveTab('bridges')} className={`px-4 py-1.5 text-xs font-bold rounded-md transition-all ${activeTab === 'bridges' ? 'bg-orange-600 text-white' : 'text-slate-400 hover:text-white'}`}>Bridges</button>
                    <button onClick={() => setActiveTab('portals')} className={`px-4 py-1.5 text-xs font-bold rounded-md transition-all ${activeTab === 'portals' ? 'bg-cyan-600 text-white' : 'text-slate-400 hover:text-white'}`}>Portals</button>
                </div>
            }
        >
            <div className="max-w-2xl mx-auto h-[500px] overflow-y-auto custom-scroll p-1">
                {activeTab === 'bridges' && renderList('bridges')}
                {activeTab === 'portals' && renderList('portals')}
                
                <div className="mt-8 p-5 bg-indigo-900/20 border border-indigo-500/30 rounded-2xl text-xs text-indigo-100 shadow-xl">
                    <h4 className="font-bold flex items-center gap-2 mb-3 text-sm text-indigo-300">
                        <Icon name="Info" weight="fill" className="text-lg" /> 
                        Internal Logic
                    </h4>
                    <div className="space-y-3 opacity-90 leading-relaxed">
                        <p>
                            <b className="text-indigo-300 uppercase tracking-wider text-[10px]">Bridge:</b> The active end (behind NAT). Initiates connection to the Portal.
                        </p>
                        <p>
                            <b className="text-indigo-300 uppercase tracking-wider text-[10px]">Portal:</b> The passive end (public server). Listens for and accepts Bridge connections.
                        </p>
                        <div className="pt-2 border-t border-indigo-500/20 text-[10px] text-indigo-400/80 italic">
                            Traffic flow: User → Portal (Passive) ↔ Bridge (Active) → Target Service.
                        </div>
                    </div>
                </div>
            </div>
        </Modal>
    );
};