// @ts-nocheck
import React from 'react';
import { Icon } from './ui/Icon';
import type { Diagnostic, DiagnosticSeverity } from '../../utils/diagnostics';

interface Props {
    diagnostics: Diagnostic[];
    onClose: () => void;
}

export const DiagnosticsPanel = ({ diagnostics, onClose }: Props) => {
    const criticals = diagnostics.filter(d => d.severity === 'critical');
    const warnings = diagnostics.filter(d => d.severity === 'warning');
    const infos = diagnostics.filter(d => d.severity === 'info');

    const SeverityIcon = ({ severity }: { severity: DiagnosticSeverity }) => {
        switch (severity) {
            case 'critical': return <Icon name="XCircle" className="text-rose-500" weight="fill" />;
            case 'warning': return <Icon name="Warning" className="text-amber-500" weight="fill" />;
            case 'info': return <Icon name="Info" className="text-blue-500" weight="fill" />;
        }
    };

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" onClick={onClose}>
            <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-2xl max-h-[80vh] flex flex-col shadow-2xl overflow-hidden" onClick={e => e.stopPropagation()}>
                {/* Header */}
                <div className="p-6 border-b border-slate-800 bg-slate-900/50 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="bg-indigo-500/20 p-2.5 rounded-xl text-indigo-400">
                            <Icon name="ShieldCheck" className="text-2xl" />
                        </div>
                        <div>
                            <h2 className="text-xl font-bold text-white tracking-tight">System Diagnostics</h2>
                            <p className="text-xs text-slate-500 uppercase font-bold tracking-widest mt-0.5">Xray Configuration Audit</p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-slate-800 rounded-full text-slate-500 transition-colors">
                        <Icon name="X" weight="bold" />
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-6 space-y-6 custom-scroll bg-slate-950/30">
                    {diagnostics.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-20 text-center">
                            <div className="w-20 h-20 bg-emerald-500/10 rounded-full flex items-center justify-center mb-4 border border-emerald-500/20">
                                <Icon name="CheckCircle" className="text-4xl text-emerald-500" weight="duotone" />
                            </div>
                            <h3 className="text-lg font-bold text-white mb-2">Configuration is Perfect!</h3>
                            <p className="text-sm text-slate-500 max-w-xs">No issues or potential conflicts detected in your current setup.</p>
                        </div>
                    ) : (
                        <>
                            {/* Summary Stats */}
                            <div className="grid grid-cols-3 gap-4 mb-2">
                                <div className="bg-slate-900/50 border border-slate-800 p-3 rounded-xl text-center">
                                    <div className="text-xl font-black text-rose-500">{criticals.length}</div>
                                    <div className="text-[10px] uppercase font-bold text-slate-500">Critical</div>
                                </div>
                                <div className="bg-slate-900/50 border border-slate-800 p-3 rounded-xl text-center">
                                    <div className="text-xl font-black text-amber-500">{warnings.length}</div>
                                    <div className="text-[10px] uppercase font-bold text-slate-500">Warnings</div>
                                </div>
                                <div className="bg-slate-900/50 border border-slate-800 p-3 rounded-xl text-center">
                                    <div className="text-xl font-black text-blue-500">{infos.length}</div>
                                    <div className="text-[10px] uppercase font-bold text-slate-500">Hints</div>
                                </div>
                            </div>

                            {/* Detailed List */}
                            <div className="space-y-3">
                                {diagnostics.map((d, i) => (
                                    <div key={i} className={`p-4 rounded-xl border flex gap-4 transition-all hover:translate-x-1 ${
                                        d.severity === 'critical' ? 'bg-rose-500/5 border-rose-500/20 shadow-lg shadow-rose-500/5' : 
                                        d.severity === 'warning' ? 'bg-amber-500/5 border-amber-500/20' : 
                                        'bg-blue-500/5 border-blue-500/20'
                                    }`}>
                                        <div className="mt-1 shrink-0">
                                            <SeverityIcon severity={d.severity} />
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2 mb-1">
                                                <span className="text-[10px] font-black uppercase px-1.5 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-400">
                                                    {d.section}{d.itemIndex !== undefined ? ` #${d.itemIndex + 1}` : ''}
                                                </span>
                                                {d.field && (
                                                    <span className="text-[10px] font-mono text-indigo-400 bg-indigo-500/5 px-1.5 rounded">
                                                        {d.field}
                                                    </span>
                                                )}
                                            </div>
                                            <p className={`text-sm font-medium ${
                                                d.severity === 'critical' ? 'text-rose-200' : 
                                                d.severity === 'warning' ? 'text-amber-200' : 
                                                'text-blue-200'
                                            }`}>
                                                {d.message}
                                            </p>
                                            {d.suggestion && (
                                                <div className="mt-2 flex items-start gap-2 text-xs text-slate-500 bg-black/20 p-2 rounded-lg border border-white/5 italic">
                                                    <Icon name="Lightbulb" className="shrink-0 mt-0.5" />
                                                    <span>{d.suggestion}</span>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </>
                    )}
                </div>

                {/* Footer */}
                <div className="p-4 border-t border-slate-800 bg-slate-900/50 flex justify-end gap-3">
                    <button onClick={onClose} className="px-6 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-bold text-sm transition-all shadow-lg active:scale-95">
                        Got it
                    </button>
                </div>
            </div>
        </div>
    );
};
