// @ts-nocheck
import React from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Icon } from '../ui/Icon';
import { useRemnawaveEditor } from '../../hooks/useRemnawaveEditor';

export const RemnawaveModal = ({ onClose }: { onClose: () => void }) => {
    const {
        remnawave,
        step,
        setStep,
        loading,
        url,
        setUrl,
        apiToken,
        setApiToken,
        profiles,
        handleRefreshProfiles,
        handleConnect,
        handleSelectProfile,
        disconnectRemnawave
    } = useRemnawaveEditor(onClose);

    return (
        <Modal 
            title={step === 'login' ? "Connect Remnawave" : "Select Profile"} 
            onClose={onClose} 
            className="max-w-md"
            onSave={onClose}
        >
            <div className="space-y-5">
                {step === 'login' ? (
                    <div className="animate-in fade-in duration-300">
                        <div className="bg-amber-900/20 p-4 rounded-xl border border-amber-500/30 text-[11px] text-amber-200/80 mb-6 flex gap-3">
                            <Icon name="ShieldCheck" className="text-xl shrink-0 text-amber-400" />
                            <p>
                                Password login is disabled for security reasons. 
                                Please use an <b>API Token</b> from your panel settings.
                            </p>
                        </div>

                        <div className="space-y-4">
                            <div>
                                <label className="label-xs">Panel URL</label>
                                <input className="input-base" 
                                    placeholder="https://panel.example.com" 
                                    value={url} onChange={e => setUrl(e.target.value)} 
                                />
                            </div>

                            <div>
                                <label className="label-xs">API Token</label>
                                <input className="input-base font-mono text-xs" 
                                    type="password"
                                    placeholder="Paste your token here..." 
                                    value={apiToken} onChange={e => setApiToken(e.target.value)} 
                                />
                            </div>

                            <Button className="w-full mt-2 py-3" onClick={handleConnect} disabled={loading}>
                                {loading ? <Icon name="Spinner" className="animate-spin" /> : "Connect & Fetch Profiles"}
                            </Button>
                        </div>
                    </div>
                ) : (
                    <div className="animate-in slide-in-from-right-4 duration-300">
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Available Profiles</h3>
                            <button onClick={handleRefreshProfiles} className="p-1 hover:bg-slate-800 rounded transition-colors text-indigo-400">
                                <Icon name="ArrowsClockwise" className={loading ? "animate-spin" : ""} />
                            </button>
                        </div>
                        
                        <div className="space-y-2 max-h-[300px] overflow-y-auto custom-scroll pr-1">
                            {profiles.map(p => (
                                <div key={p.uuid} 
                                    onClick={() => handleSelectProfile(p.uuid)}
                                    className={`p-3 border rounded-xl cursor-pointer transition-all flex justify-between items-center group
                                        ${remnawave.activeProfileUuid === p.uuid 
                                            ? 'bg-indigo-600/20 border-indigo-500 shadow-[0_0_15px_rgba(79,70,229,0.1)]' 
                                            : 'bg-slate-900 border-slate-800 hover:border-slate-600'}
                                    `}
                                >
                                    <div className="flex items-center gap-3">
                                        <div className={`w-2 h-2 rounded-full ${remnawave.activeProfileUuid === p.uuid ? 'bg-indigo-400 shadow-[0_0_8px_rgba(129,140,248,0.6)]' : 'bg-slate-700'}`}></div>
                                        <span className={`font-mono text-sm ${remnawave.activeProfileUuid === p.uuid ? 'text-white font-bold' : 'text-slate-300'}`}>
                                            {p.name}
                                        </span>
                                    </div>
                                    {remnawave.activeProfileUuid === p.uuid ? (
                                        <Icon name="CheckCircle" weight="fill" className="text-emerald-400" />
                                    ) : (
                                        <Icon name="ArrowRight" className="text-slate-600 md:opacity-0 md:group-hover:opacity-100 transition-opacity" />
                                    )}
                                </div>
                            ))}
                        </div>

                        <div className="mt-6 pt-4 border-t border-slate-800 flex justify-between gap-3">
                             <Button variant="ghost" onClick={() => disconnectRemnawave()} className="text-xs text-rose-400 hover:bg-rose-500/10">
                                <Icon name="LinkBreak" /> Disconnect
                            </Button>
                             <Button variant="secondary" onClick={() => setStep('login')} className="text-xs">
                                <Icon name="UserSwitch" /> Change URL
                            </Button>
                        </div>
                    </div>
                )}
            </div>
        </Modal>
    );
};