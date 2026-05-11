// @ts-nocheck
import React from 'react';
import { Icon } from '../ui/Icon';
import { Button } from '../ui/Button';
import { EditorLayout } from '../ui/EditorLayout';
import { Card } from '../ui/Card';
import { Select } from '../ui/Select';
import { FormField } from '../ui/FormField';

import { LogEditor } from './settings/LogEditor';
import { ApiStatsEditor } from './settings/ApiStatsEditor';
import { PolicyEditor } from './settings/PolicyEditor';
import { ObservatoryEditor } from './settings/ObservatoryEditor';
import { BurstObservatoryEditor } from './settings/BurstObservatoryEditor';

import { useSettingsEditor } from '../../hooks/useSettingsEditor';
import { useConfigStore } from '../../store/configStore';

export const SettingsModal = ({ onClose }: { onClose: () => void }) => {
    const { warpWorkerUrl, setWarpWorkerUrl } = useConfigStore();
    const {
        coreVersion,
        setCoreVersion,
        activeTab,
        setActiveTab,
        rawMode,
        setRawMode,
        outboundTags,
        coreSettings,
        handleRawUpdate,
        downloadCoreJson,
        config,
        updateSection,
        toggleSection
    } = useSettingsEditor();

    const tabs = (
        <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800 shrink-0">
            <button onClick={() => setActiveTab('general')} className={`px-4 py-1.5 text-[10px] font-bold uppercase tracking-wider rounded transition-all ${activeTab === 'general' ? 'bg-indigo-600 text-white shadow' : 'text-slate-500 hover:text-slate-300'}`}>Log & API</button>
            <button onClick={() => setActiveTab('policy')} className={`px-4 py-1.5 text-[10px] font-bold uppercase tracking-wider rounded transition-all ${activeTab === 'policy' ? 'bg-indigo-600 text-white shadow' : 'text-slate-500 hover:text-slate-300'}`}>Policy</button>
            <button onClick={() => setActiveTab('observatory')} className={`px-4 py-1.5 text-[10px] font-bold uppercase tracking-wider rounded transition-all ${activeTab === 'observatory' ? 'bg-indigo-600 text-white shadow' : 'text-slate-500 hover:text-slate-300'}`}>Observatory</button>
        </div>
    );

    const extraButtons = (
        <>
            {!rawMode && tabs}
            <Button variant="success" className="text-xs py-1" onClick={downloadCoreJson} icon="DownloadSimple">Export</Button>
        </>
    );

    return (
        <EditorLayout
            title="Общие настройки"
            local={coreSettings}
            setLocal={handleRawUpdate}
            rawMode={rawMode}
            setRawMode={setRawMode}
            errors={[]}
            onSave={onClose}
            onClose={onClose}
            schemaMode="full"
            extraButtons={extraButtons}
        >
            <div className="max-w-3xl mx-auto space-y-6">
                {activeTab === 'general' && (
                    <>
                        <Card title="Совместимость ядра и генераторы" icon="Cpu">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <Select 
                                    label="Target Xray-core Version"
                                    hint="Adjusts UI fields and validation based on core features."
                                    value={coreVersion}
                                    onChange={val => setCoreVersion(val)}
                                    options={[
                                        { value: "v1.8.10", label: "Latest (v1.8.10+)" },
                                        { value: "v1.8.0", label: "Stable (v1.8.0)" },
                                        { value: "v1.5.0", label: "Legacy (v1.5.0)" },
                                    ]}
                                />
                                <FormField label="URL WARP-воркера" help="Опционально: URL приватного Cloudflare Worker для CORS-безопасной регистрации.">
                                    <input 
                                        className="input-base"
                                        placeholder="https://your-worker.workers.dev"
                                        value={warpWorkerUrl}
                                        onChange={e => setWarpWorkerUrl(e.target.value)}
                                    />
                                </FormField>
                            </div>
                        </Card>
                        
                        <LogEditor 
                            log={config?.log} 
                            onChange={(v: any) => updateSection('log', v)} 
                            onToggle={(d: any) => toggleSection('log', d)} 
                        />
                        
                        <ApiStatsEditor 
                            api={config?.api} 
                            stats={config?.stats}
                            onUpdateApi={(v: any) => updateSection('api', v)}
                            onToggleApi={(d: any) => toggleSection('api', d)}
                            onToggleStats={(d: any) => toggleSection('stats', d)}
                        />
                    </>
                )}

                {activeTab === 'policy' && (
                    <PolicyEditor 
                        policy={config?.policy} 
                        onChange={(v: any) => updateSection('policy', v)}
                        onToggle={(d: any) => toggleSection('policy', d)}
                    />
                )}

                {activeTab === 'observatory' && (
                    <div className="space-y-6">
                        <div className="p-3 bg-indigo-900/10 border border-indigo-500/20 rounded-xl text-[11px] text-indigo-300 flex items-start gap-2">
                            <Icon name="Info" className="shrink-0 mt-0.5" />
                            <span>Use <b>Observatory</b> for standard periodic checks, or <b>Burst Observatory</b> for randomized stealth checks. Choose one based on your balancers setup.</span>
                        </div>
                        
                        <ObservatoryEditor 
                            observatory={config?.observatory}
                            outboundTags={outboundTags}
                            onChange={(v: any) => updateSection('observatory', v)}
                            onToggle={(d: any) => toggleSection('observatory', d)}
                        />
                        
                        <BurstObservatoryEditor 
                            burstObservatory={config?.burstObservatory}
                            outboundTags={outboundTags}
                            onChange={(v: any) => updateSection('burstObservatory', v)}
                            onToggle={(d: any) => toggleSection('burstObservatory', d)}
                        />
                    </div>
                )}
            </div>
        </EditorLayout>
    );
};
