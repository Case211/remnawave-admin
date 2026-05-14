// @ts-nocheck
import React from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Select } from '../ui/Select';
import { useConfigStore } from '../../store/configStore';
import { Icon } from '../ui/Icon';

import { RuleList } from './routing/RuleList';
import { RuleEditor } from './routing/RuleEditor';
import { BalancerList } from './routing/BalancerList';
import { BalancerEditor } from './routing/BalancerEditor';

import { useRoutingEditor } from '../../hooks/useRoutingEditor';
import { useGeoData } from '../../hooks/useGeoData';
import { useSidebarResizer } from '../../hooks/useSidebarResizer';

export const RoutingModal = ({ onClose }: any) => {
    const { config, updateSection } = useConfigStore();
    
    const {
        rules,
        balancers,
        outboundTags,
        inboundTags,
        balancerTags,
        activeTab,
        setActiveTab,
        activeRuleIdx,
        activeBalancerIdx,
        setActiveBalancerIdx,
        rawMode,
        setRawMode,
        mobileEditMode,
        setMobileEditMode,
        searchQuery,
        setSearchQuery,
        brokenRules,
        hasCriticalErrors,
        handleClose,
        filteredRules,
        handleSelectRule,
        handleAddRule,
        handleDeleteRule,
        handleUpdateRule,
        handleAddBalancer,
        handleUpdateBalancer,
        handleDeleteBalancer
    } = useRoutingEditor(onClose);

    const { geoSites, geoIps, loadingGeo } = useGeoData();
    const { sidebarWidth, startResizing } = useSidebarResizer();

    return (
        <Modal
            title="Маршрутизация"
            onClose={handleClose}
            onSave={handleClose}
            extraButtons={
                <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800">
                    <button
                        onClick={() => { setActiveTab('rules'); setMobileEditMode(false); }}
                        className={`px-4 py-1.5 text-xs font-bold rounded-md transition-all ${activeTab === 'rules' ? 'bg-indigo-600 text-white' : 'text-slate-400'}`}
                    >Rules</button>
                    <button
                        onClick={() => { setActiveTab('balancers'); setMobileEditMode(false); }}
                        className={`px-4 py-1.5 text-xs font-bold rounded-md transition-all ${activeTab === 'balancers' ? 'bg-purple-600 text-white' : 'text-slate-400'}`}
                    >Balancers</button>
                </div>
            }
        >
            <div className="mb-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                {mobileEditMode && (
                    <Button variant="secondary" className="md:hidden w-full" onClick={() => setMobileEditMode(false)} icon="ArrowLeft">Back</Button>
                )}
                <div className={`flex flex-col w-full md:w-64 ${mobileEditMode ? 'hidden md:flex' : ''}`}>
                    <Select
                        label="Стратегия доменов"
                        value={config?.routing?.domainStrategy || "AsIs"}
                        onChange={val => updateSection('routing', { ...config?.routing, domainStrategy: val })}
                        options={[
                            { value: "AsIs", label: "AsIs", description: "Use domain as provided" },
                            { value: "IPIfNonMatch", label: "IPIfNonMatch", description: "Resolve if no domain match" },
                            { value: "IPOnDemand", label: "IPOnDemand", description: "Resolve before matching" },
                        ]}
                    />
                </div>

                {((activeTab === 'rules' && activeRuleIdx !== null) || (activeTab === 'balancers' && activeBalancerIdx !== null)) && (
                    <Button
                        variant="secondary"
                        className={`text-xs py-1 ${mobileEditMode ? 'w-full md:w-auto' : 'hidden md:flex'}`}
                        onClick={() => setRawMode(!rawMode)}
                        icon={rawMode ? "Layout" : "Code"}
                    >
                        {rawMode ? "UI Mode" : "JSON"}
                    </Button>
                )}
            </div>

            {hasCriticalErrors && (
                <div className="mb-4 p-3.5 bg-rose-950/50 border border-rose-500/60 rounded-xl animate-in fade-in">
                    <div className="flex items-start gap-2.5">
                        <Icon name="WarningOctagon" weight="fill" className="text-rose-400 text-xl shrink-0 mt-0.5" />
                        <div className="flex-1 min-w-0">
                            <p className="text-rose-200 font-bold text-sm mb-1">
                                Cannot close — {brokenRules.length} rule{brokenRules.length > 1 ? 's have' : ' has'} errors that will crash Xray
                            </p>
                            <p className="text-rose-300/60 text-[11px] mb-2">
                                Click a rule below to jump to it and fix the issue.
                            </p>
                            <ul className="space-y-1">
                                {brokenRules.map(r => (
                                    <li key={r.idx}>
                                        <button
                                            className="text-[11px] text-left w-full text-rose-300 hover:text-white bg-rose-900/30 hover:bg-rose-800/50 border border-rose-700/40 rounded-lg px-3 py-1.5 transition-colors flex items-start gap-2"
                                            onClick={() => {
                                                setActiveTab('rules');
                                                handleSelectRule(r.idx);
                                            }}
                                        >
                                            <Icon name="ArrowRight" className="shrink-0 mt-0.5" />
                                            <span>
                                                <b className="text-rose-200">{r.label}</b>
                                                {" — "}
                                                {r.errors[0].message}
                                                {r.errors.length > 1 && <span className="text-rose-400/60"> (+{r.errors.length - 1} more)</span>}
                                            </span>
                                        </button>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    </div>
                </div>
            )}

            <div
                className="flex flex-col md:flex-row h-[60vh] adaptive-height border border-slate-800 rounded-2xl overflow-hidden bg-slate-900 shadow-2xl relative"
                style={{ '--sidebar-width': `${sidebarWidth}px` } as any}
            >
                {activeTab === 'rules' ? (
                    <>
                        <div className={`w-full md:w-[var(--sidebar-width)] bg-slate-950 border-r border-slate-800 flex flex-col h-full shrink-0 ${mobileEditMode ? 'hidden md:flex' : 'flex'}`}>
                            <div className="p-3 border-b border-slate-800 space-y-3 bg-slate-900/50">
                                <div className="flex justify-between items-center">
                                    <span className="text-xs font-bold text-slate-400 pl-2 uppercase tracking-widest">Rules</span>
                                    <Button variant="ghost" icon="Plus" className="py-1 px-2" onClick={handleAddRule} />
                                </div>
                                <div className="relative">
                                    <Icon name="MagnifyingGlass" className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-600 text-xs" />
                                    <input
                                        className="w-full bg-slate-950 border border-slate-700 rounded-md pl-8 pr-2 py-1.5 text-[11px] text-white outline-none focus:border-indigo-500 transition-colors"
                                        placeholder="Поиск по имени, домену, IP..."
                                        value={searchQuery}
                                        onChange={e => setSearchQuery(e.target.value)}
                                    />
                                </div>
                            </div>
                            <RuleList
                                rules={filteredRules}
                                activeIndex={activeRuleIdx}
                                onSelect={(idx: number) => handleSelectRule(filteredRules[idx].originalIndex)}
                                onDelete={(idx: number) => handleDeleteRule(filteredRules[idx].originalIndex)}
                                onReorder={searchQuery ? undefined : (newRules: any) => {
                                    useConfigStore.getState().reorderRules(newRules.map(({ originalIndex: _, ...rest }: any) => rest));
                                }}
                            />
                        </div>

                        <div className="hidden md:block w-1 bg-slate-800 hover:bg-indigo-500 cursor-col-resize z-10 shrink-0" onMouseDown={startResizing} />

                        <div className={`flex-1 flex flex-col h-full bg-slate-900/50 min-w-0 ${mobileEditMode ? 'flex' : 'hidden md:flex'}`}>
                            <RuleEditor
                                rule={rules[activeRuleIdx!]}
                                onChange={handleUpdateRule}
                                outboundTags={outboundTags}
                                balancerTags={balancerTags}
                                inboundTags={inboundTags}
                                geoData={{ sites: geoSites, ips: geoIps, loading: loadingGeo }}
                                rawMode={rawMode}
                            />
                        </div>
                    </>
                ) : (
                    <>
                        <div className={`w-full md:w-[var(--sidebar-width)] bg-slate-950 border-r border-slate-800 flex flex-col h-full shrink-0 ${mobileEditMode ? 'hidden md:flex' : 'flex'}`}>
                            <div className="p-3 border-b border-slate-800 flex justify-between bg-slate-900/50 items-center">
                                <span className="text-xs font-bold text-slate-400 pl-2 uppercase tracking-widest">Balancers</span>
                                <Button variant="ghost" icon="Plus" className="py-1 px-2" onClick={handleAddBalancer} />
                            </div>
                            <BalancerList
                                balancers={balancers}
                                activeIndex={activeBalancerIdx}
                                onSelect={(idx: number) => { setActiveBalancerIdx(idx); setMobileEditMode(true); }}
                                onDelete={handleDeleteBalancer}
                            />
                        </div>

                        <div className="hidden md:block w-1 bg-slate-800 hover:bg-indigo-500 cursor-col-resize z-10 shrink-0" onMouseDown={startResizing} />

                        <div className={`flex-1 flex flex-col h-full bg-slate-900/50 min-w-0 ${mobileEditMode ? 'flex' : 'hidden md:flex'}`}>
                            <BalancerEditor
                                balancer={balancers[activeBalancerIdx!]}
                                onChange={handleUpdateBalancer}
                                outboundTags={outboundTags}
                                rawMode={rawMode}
                            />
                        </div>
                    </>
                )}
            </div>
        </Modal>
    );
};