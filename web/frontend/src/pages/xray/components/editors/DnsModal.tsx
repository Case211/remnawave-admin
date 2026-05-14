// @ts-nocheck
import React from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { JsonField } from '../ui/JsonField';

// Sub-components
import { DnsGeneral } from './dns/DnsGeneral';
import { DnsServers } from './dns/DnsServers';
import { DnsServerEditor } from './dns/DnsServerEditor';
import { DnsHosts } from './dns/DnsHosts';
import { DnsFakedns } from './dns/DnsFakedns';

import { useDnsEditor } from '../../hooks/useDnsEditor';

export const DnsModal = ({ onClose }: any) => {
    const {
        dns,
        fakedns,
        activeTab,
        setActiveTab,
        editingServerIdx,
        setEditingServerIdx,
        rawMode,
        setRawMode,
        mobileEditMode,
        setMobileEditMode,
        handleUpdateDns,
        handleAddServer,
        handleSelectServer,
        handleDeleteServer,
        handleUpdateServer,
        handleCompositeUpdate,
        updateHosts,
        updateFakedns
    } = useDnsEditor();

    // --- JSON MODE VIEW ---
    if (rawMode) {
        const compositeConfig = { dns: dns, fakedns: fakedns };

        return (
            <Modal
                title="DNS & FakeDNS (JSON)"
                onClose={onClose}
                onSave={() => onClose()}
                extraButtons={<Button variant="secondary" className="text-xs py-1" onClick={() => setRawMode(false)} icon="Layout">Form Mode</Button>}
            >
                <div className="h-[500px] flex flex-col gap-2">
                    <div className="bg-slate-800/50 border border-slate-700/50 p-2 rounded text-[10px] text-slate-400">
                        This editor manages both <code>dns</code> and <code>fakedns</code> root sections simultaneously.
                    </div>
                    <JsonField
                        label="Совмещённая конфигурация"
                        value={compositeConfig}
                        onChange={handleCompositeUpdate}
                        className="flex-1"
                        schemaMode="full"
                    />
                </div>
            </Modal>
        );
    }

    // --- FORM MODE VIEW ---
    return (
        <Modal
            title="Настройка DNS"
            onClose={onClose}
            onSave={() => onClose()}
            className="md:max-w-[1000px]"
            extraButtons={
                <div className="flex gap-2 w-full md:w-auto overflow-x-auto pb-1 md:pb-0 hide-scrollbar">
                    <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800 shrink-0">
                        <button onClick={() => { setActiveTab('general'); setEditingServerIdx(null); setMobileEditMode(false); }}
                            className={`px-3 py-1.5 text-xs font-bold rounded transition-all ${activeTab === 'general' ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-white'}`}>General</button>
                        <button onClick={() => { setActiveTab('servers'); setEditingServerIdx(null); setMobileEditMode(false); }}
                            className={`px-3 py-1.5 text-xs font-bold rounded transition-all ${activeTab === 'servers' ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-white'}`}>Servers</button>
                        <button onClick={() => { setActiveTab('hosts'); setEditingServerIdx(null); setMobileEditMode(false); }}
                            className={`px-3 py-1.5 text-xs font-bold rounded transition-all ${activeTab === 'hosts' ? 'bg-emerald-600 text-white shadow' : 'text-slate-400 hover:text-white'}`}>Hosts</button>
                        <button onClick={() => { setActiveTab('fakedns'); setEditingServerIdx(null); setMobileEditMode(false); }}
                            className={`px-3 py-1.5 text-xs font-bold rounded transition-all ${activeTab === 'fakedns' ? 'bg-purple-600 text-white shadow' : 'text-slate-400 hover:text-white'}`}>FakeDNS</button>
                    </div>
                    <Button variant="secondary" className="text-xs py-1 shrink-0" onClick={() => setRawMode(true)} icon="Code">JSON</Button>
                </div>
            }
        >
            <div className="h-[500px] md:h-[500px] flex flex-col md:flex-row gap-6">

                {/* --- GENERAL TAB --- */}
                {activeTab === 'general' && (
                    <div className="w-full max-w-2xl mx-auto overflow-y-auto custom-scroll">
                        <DnsGeneral dns={dns} onChange={handleUpdateDns} />
                    </div>
                )}

                {/* --- HOSTS TAB --- */}
                {activeTab === 'hosts' && (
                    <div className="w-full max-w-2xl mx-auto overflow-y-auto custom-scroll">
                        <DnsHosts hosts={dns.hosts} onChange={updateHosts} />
                    </div>
                )}

                {/* --- FAKEDNS TAB --- */}
                {activeTab === 'fakedns' && (
                    <div className="w-full max-w-2xl mx-auto overflow-y-auto custom-scroll">
                        <DnsFakedns fakedns={fakedns} onChange={updateFakedns} />
                    </div>
                )}

                {/* --- SERVERS TAB (Split View) --- */}
                {activeTab === 'servers' && (
                    <>
                        {/* Mobile Back Button */}
                        {mobileEditMode && (
                            <div className="md:hidden w-full pb-2">
                                <Button variant="secondary" className="w-full text-xs" onClick={() => setMobileEditMode(false)} icon="ArrowLeft">Back to Servers</Button>
                            </div>
                        )}

                        {/* List Column (Hidden on mobile if editing) */}
                        <div className={`${mobileEditMode ? 'hidden md:block' : 'block'} ${editingServerIdx !== null ? 'w-full md:w-1/3' : 'w-full max-w-2xl mx-auto'} transition-all duration-300 h-full overflow-hidden flex flex-col`}>
                            <DnsServers
                                servers={dns.servers}
                                onSelect={handleSelectServer}
                                onAdd={handleAddServer}
                                onDelete={handleDeleteServer}
                                onReorder={(newServers) => handleUpdateDns({ ...dns, servers: newServers })}
                            />
                        </div>

                        {/* Editor Column (Hidden on mobile if NOT editing) */}
                        {editingServerIdx !== null && (
                            <div className={`${mobileEditMode ? 'block' : 'hidden md:block'} flex-1 animate-in slide-in-from-right-4 fade-in duration-300 h-full overflow-hidden flex flex-col`}>
                                <DnsServerEditor
                                    server={dns.servers?.[editingServerIdx]}
                                    onChange={handleUpdateServer}
                                    onCancel={() => { setEditingServerIdx(null); setMobileEditMode(false); }}
                                />
                            </div>
                        )}
                    </>
                )}
            </div>
        </Modal>
    );
};