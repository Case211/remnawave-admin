// @ts-nocheck
import React, { useState, useMemo } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Icon } from '../ui/Icon';
import { useConfigStore } from '../../store/configStore';
import { toast } from 'sonner';

export const ConfigInspectorModal = ({ onClose, setModal, openSectionJson }: { 
    onClose: () => void, 
    setModal: (m: any) => void,
    openSectionJson: (section: string, title: string, data: any) => void 
}) => {
    const { config: currentConfig, addOutbounds, updateSection, addItem } = useConfigStore();
    const [inputText, setInputText] = useState("");
    const [subUrl, setSubUrl] = useState("");
    const [isFetching, setIsFetching] = useState(false);
    const [parsedConfigs, setParsedConfigs] = useState<any[] | null>(null);
    const [selectedIndex, setSelectedIndex] = useState(0);

    const handleFetchSub = async () => {
        if (!subUrl.trim()) return;
        setIsFetching(true);
        try {
            const targetUrl = subUrl.trim();
            const proxyUrl = `https://crs.bropines.workers.dev/${targetUrl}`;
            
            const headers: Record<string, string> = {
                "x-custom-user-agent": "v2rayNG/1.8.5"
            };

            const response = await fetch(proxyUrl, { headers });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const rawText = await response.text();
            let decoded = rawText.trim();
            
            if (!decoded.startsWith('{') && !decoded.startsWith('[')) {
                try {
                    let b64 = decoded.replace(/\s/g, '');
                    while (b64.length % 4 !== 0) b64 += '=';
                    decoded = atob(b64);
                    try { decoded = decodeURIComponent(escape(decoded)); } catch (e) {}
                } catch (e) {
                    decoded = rawText.trim();
                }
            }
            
            setInputText(decoded);
            toast.success("Subscription fetched successfully");
        } catch (error: any) {
            toast.error("Fetch failed", { description: error.message });
        } finally {
            setIsFetching(false);
        }
    };

    const handleParse = () => {
        try {
            const data = JSON.parse(inputText);
            const configs = Array.isArray(data) ? data : [data];
            if (configs.some(c => !c || typeof c !== 'object')) throw new Error("Invalid format");
            setParsedConfigs(configs);
            setSelectedIndex(0);
            toast.success(`Analyzed ${configs.length} configurations`);
        } catch (e: any) {
            toast.error("Parse failed", { description: e.message });
        }
    };

    const selectedConfig = useMemo(() => {
        if (!parsedConfigs || !parsedConfigs[selectedIndex]) return null;
        return parsedConfigs[selectedIndex];
    }, [parsedConfigs, selectedIndex]);

    const importOutbound = (proxy: any, customTag?: string) => {
        addOutbounds([{ ...proxy, tag: customTag || proxy.tag }]);
        toast.success("Node added to outbounds");
    };

    const openInboundEditor = (ib: any) => {
        setModal({ type: 'inbound', data: ib, index: null });
    };

    const openOutboundEditor = (ob: any) => {
        setModal({ type: 'outbound', data: ob, index: null });
    };

    const importRoutingItem = (section: 'rules' | 'balancers', item: any) => {
        const currentRouting = currentConfig?.routing || { rules: [], balancers: [] };
        const updated = {
            ...currentRouting,
            [section]: [item, ...(currentRouting[section] || [])]
        };
        updateSection('routing', updated);
        toast.success(`Imported to your routing (at the top)`);
    };

    const extractAllFromSelected = () => {
        if (!selectedConfig) return;
        const proxies = (selectedConfig.outbounds || []).filter((o: any) => 
            !['freedom', 'dns', 'blackhole', 'direct', 'block'].includes(o.protocol)
        );
        const name = selectedConfig.remarks || "Config";
        const cleaned = proxies.map((p: any, i: number) => ({
            ...p,
            tag: proxies.length > 1 ? `${name}-${i + 1}` : name
        }));
        addOutbounds(cleaned);
        toast.success(`Extracted ${cleaned.length} nodes from ${name}`);
    };

    return (
        <Modal title="Инспектор конфигов" onClose={onClose} className="max-w-[95vw] 2xl:max-w-[1600px]" hideSave>
            <div className="h-[80vh] flex flex-col min-h-[600px]">
                {!parsedConfigs ? (
                    <div className="flex-1 flex flex-col max-w-4xl mx-auto w-full space-y-6 py-6">
                        <div className="text-center space-y-3 shrink-0">
                            <div className="w-20 h-20 bg-indigo-500/10 rounded-3xl flex items-center justify-center mx-auto border border-indigo-500/20 shadow-inner">
                                <Icon name="Briefcase" className="text-4xl text-indigo-400" />
                            </div>
                            <h3 className="text-2xl font-black text-white italic tracking-tight">Configuration Harvester</h3>
                            <p className="text-slate-500 text-sm max-w-md mx-auto leading-relaxed">
                                Paste a single Xray JSON or an array of configurations to start surgical extraction of components.
                            </p>
                        </div>
                        <div className="flex gap-2 shrink-0">
                            <input
                                type="text"
                                className="flex-1 bg-slate-950 border border-slate-800 rounded-2xl px-5 text-sm font-mono text-white outline-none focus:border-indigo-500 transition-all shadow-inner"
                                placeholder="https://example.com/subscription.json"
                                value={subUrl}
                                onChange={(e) => setSubUrl(e.target.value)}
                            />
                            <Button variant="secondary" className="px-8 rounded-2xl border-indigo-500/30 text-indigo-400 hover:bg-indigo-500/10 shadow-lg" onClick={handleFetchSub} disabled={!subUrl.trim() || isFetching} icon="CloudArrowDown">
                                {isFetching ? "Fetching..." : "Fetch Remote"}
                            </Button>
                        </div>
                        <div className="relative group flex-1 flex flex-col min-h-[350px]">
                            <div className="absolute -inset-1 bg-gradient-to-r from-indigo-500 to-purple-600 rounded-3xl blur opacity-25 group-hover:opacity-40 transition duration-1000"></div>
                            <textarea 
                                className="flex-1 relative w-full bg-slate-950 border border-slate-800 rounded-2xl p-5 text-[12px] font-mono text-indigo-100 focus:border-indigo-500 outline-none resize-none custom-scroll shadow-2xl transition-all"
                                placeholder='Paste your JSON configuration array here, or fetch from a URL above...'
                                value={inputText}
                                onChange={e => setInputText(e.target.value)}
                            />
                        </div>
                        <Button className="w-full py-4 shrink-0 text-base font-black uppercase tracking-widest shadow-2xl shadow-indigo-500/20 rounded-2xl bg-indigo-600 hover:bg-indigo-500 border-none" onClick={handleParse} disabled={!inputText.trim()} icon="Lightning">
                            Analyze All Components
                        </Button>
                    </div>
                ) : (
                    <div className="flex-1 flex overflow-hidden gap-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
                        {/* Sidebar: Navigation */}
                        <div className="w-80 shrink-0 flex flex-col bg-slate-900/40 border border-slate-800/60 rounded-3xl overflow-hidden shadow-2xl">
                            <div className="p-5 border-b border-slate-800/60 bg-slate-950/40 flex justify-between items-center">
                                <div className="flex flex-col">
                                    <span className="text-[10px] font-black text-slate-500 uppercase tracking-widest leading-none">Source Index</span>
                                    <span className="text-xs font-bold text-white mt-1">{parsedConfigs.length} Objects Found</span>
                                </div>
                                <Button variant="ghost" size="sm" className="h-8 w-8 p-0 bg-slate-800/50 hover:bg-rose-500/20 hover:text-rose-400" onClick={() => setParsedConfigs(null)} title="Очистить">
                                    <Icon name="Trash" />
                                </Button>
                            </div>
                            <div className="flex-1 overflow-y-auto custom-scroll p-3 space-y-2">
                                {parsedConfigs.map((c, i) => (
                                    <button
                                        key={i}
                                        onClick={() => setSelectedIndex(i)}
                                        className={`w-full text-left p-4 rounded-2xl transition-all border ${
                                            selectedIndex === i 
                                            ? 'bg-gradient-to-br from-indigo-600 to-indigo-700 border-indigo-500 text-white shadow-xl scale-[1.02]' 
                                            : 'bg-slate-950/40 border-slate-800/50 text-slate-400 hover:border-slate-600 hover:bg-slate-900/60'
                                        }`}
                                    >
                                        <div className="text-xs font-black truncate leading-none mb-2">{c.remarks || `Object #${i + 1}`}</div>
                                        <div className="flex gap-3 items-center opacity-70">
                                            <div className="flex items-center gap-1 text-[9px] font-bold text-emerald-400">
                                                <Icon name="ArrowCircleDown" weight="fill" /> {c.inbounds?.length || 0}
                                            </div>
                                            <div className="flex items-center gap-1 text-[9px] font-bold text-indigo-300">
                                                <Icon name="PaperPlaneRight" weight="fill" /> {c.outbounds?.length || 0}
                                            </div>
                                            <div className="flex items-center gap-1 text-[9px] font-bold text-purple-400">
                                                <Icon name="ArrowsSplit" weight="fill" /> {c.routing?.rules?.length || 0}
                                            </div>
                                        </div>
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Content: Harvesting Board */}
                        <div className="flex-1 flex flex-col min-w-0 gap-6">
                            {/* Dashboard Header */}
                            <div className="bg-slate-900/60 border border-slate-800/60 p-5 rounded-3xl flex justify-between items-center shadow-xl backdrop-blur-xl">
                                <div className="min-w-0 flex items-center gap-4">
                                    <div className="w-12 h-12 rounded-2xl bg-slate-800 flex items-center justify-center text-white shadow-lg border border-slate-700">
                                        <Icon name="Target" className="text-2xl" weight="duotone" />
                                    </div>
                                    <div>
                                        <h3 className="text-2xl font-black text-white italic tracking-tighter truncate leading-none">
                                            {selectedConfig?.remarks || "Harvester Target"}
                                        </h3>
                                        <p className="text-[10px] text-slate-500 font-bold uppercase tracking-widest mt-1">
                                            Source #{selectedIndex + 1} • {parsedConfigs.length} total
                                        </p>
                                    </div>
                                </div>
                                <div className="flex gap-3">
                                    <Button variant="secondary" className="px-4 bg-slate-800 border-slate-700 text-xs font-bold" onClick={() => openSectionJson('full', 'Source JSON', selectedConfig)} icon="Code">
                                        RAW JSON
                                    </Button>
                                    <Button variant="success" className="px-6 shadow-lg shadow-emerald-500/10 text-xs font-black uppercase" onClick={extractAllFromSelected} icon="DownloadSimple">
                                        Harvest Selected Config
                                    </Button>
                                </div>
                            </div>

                            {/* Harvesting Grid */}
                            <div className="flex-1 overflow-y-auto custom-scroll pr-3 space-y-8 pb-20">
                                {/* Inbounds Grid */}
                                <div className="space-y-4">
                                    <div className="flex items-center gap-4">
                                        <div className="h-px flex-1 bg-gradient-to-r from-emerald-500/40 to-transparent"></div>
                                        <h4 className="text-[11px] font-black text-emerald-400 uppercase tracking-[0.3em] flex items-center gap-2">
                                            <Icon name="ArrowCircleDown" weight="fill" /> Inbound Harvester
                                        </h4>
                                        <div className="h-px flex-1 bg-gradient-to-l from-emerald-500/40 to-transparent"></div>
                                    </div>
                                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                                        {(selectedConfig?.inbounds || []).map((ib: any, i: number) => (
                                            <div key={i} className="bg-emerald-500/20 border border-emerald-500/40 p-4 rounded-2xl flex justify-between items-center group hover:border-emerald-500/60 hover:bg-emerald-500/20 transition-all shadow-lg text-left">
                                                <div className="min-w-0">
                                                    <div className="text-[12px] font-black text-slate-200 truncate">{ib.tag}</div>
                                                    <div className="flex items-center gap-2 mt-1">
                                                        <span className="text-[9px] font-black text-emerald-500 uppercase bg-emerald-500/10 px-2 py-0.5 rounded-full">{ib.protocol}</span>
                                                        <span className="text-[10px] text-slate-500 font-mono font-bold">PORT {ib.port}</span>
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-1.5 opacity-60 group-hover:opacity-100 transition-all duration-300 translate-x-2 group-hover:translate-x-0">
                                                                                                    <button onClick={() => openSectionJson('inbound', `JSON: ${ib.tag}`, ib)} title="Редактировать JSON" className="p-2 rounded-md bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"><Icon name="Code" weight="bold" /></button>
                                                                                                    <button onClick={() => openInboundEditor(ib)} title="Открыть в редакторе" className="p-2 rounded-md bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"><Icon name="PencilSimple" weight="bold" /></button>
                                                                                                    <button onClick={() => { addItem('inbounds', ib); toast.success("Inbound added"); }} title="Добавить в конфиг" className="p-2 rounded-md bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500 hover:text-white transition-all"><Icon name="Plus" weight="bold" /></button>
                                                                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>

                                {/* Outbounds Grid */}
                                <div className="space-y-4">
                                    <div className="flex items-center gap-4">
                                        <div className="h-px flex-1 bg-gradient-to-r from-indigo-500/40 to-transparent"></div>
                                        <h4 className="text-[11px] font-black text-indigo-400 uppercase tracking-[0.3em] flex items-center gap-2">
                                            <Icon name="PaperPlaneRight" weight="fill" /> Outbound Harvester
                                        </h4>
                                        <div className="h-px flex-1 bg-gradient-to-l from-indigo-500/40 to-transparent"></div>
                                    </div>
                                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                                        {(selectedConfig?.outbounds || []).filter((o: any) => !['freedom', 'blackhole', 'dns'].includes(o.protocol)).map((ob: any, i: number) => (
                                            <div key={i} className="bg-indigo-500/10 border border-indigo-500/30 p-4 rounded-2xl flex justify-between items-center group hover:border-indigo-500/60 hover:bg-indigo-500/20 transition-all shadow-lg text-left">
                                                <div className="min-w-0">
                                                    <div className="text-[12px] font-black text-slate-200 truncate">{ob.tag}</div>
                                                    <div className="flex items-center gap-2 mt-1">
                                                        <span className="text-[9px] font-black text-indigo-400 uppercase bg-indigo-500/10 px-2 py-0.5 rounded-full">{ob.protocol}</span>
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-1.5 opacity-60 group-hover:opacity-100 transition-all duration-300 translate-x-2 group-hover:translate-x-0">
                                                                                                    <button onClick={() => openSectionJson('outbound', `JSON: ${ob.tag}`, ob)} title="Редактировать JSON" className="p-2 rounded-md bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"><Icon name="Code" weight="bold" /></button>
                                                                                                    <button onClick={() => openOutboundEditor(ob)} title="Открыть в редакторе" className="p-2 rounded-md bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"><Icon name="PencilSimple" weight="bold" /></button>
                                                                                                    <button onClick={() => importOutbound(ob)} title="Добавить в конфиг" className="p-2 rounded-md bg-indigo-500/20 text-indigo-400 hover:bg-indigo-500 hover:text-white transition-all"><Icon name="Plus" weight="bold" /></button>
                                                                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>

                                {/* Routing Modules Row */}
                                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                                    {/* Routing Section */}
                                    <div className="space-y-4">
                                        <div className="flex items-center gap-4">
                                            <div className="h-px flex-1 bg-gradient-to-r from-purple-500/40 to-transparent"></div>
                                            <h4 className="text-[11px] font-black text-purple-400 uppercase tracking-[0.3em] flex items-center gap-2">
                                                <Icon name="ArrowsSplit" weight="fill" /> Rules
                                            </h4>
                                            <div className="h-px flex-1 bg-transparent"></div>
                                        </div>
                                        <div className="space-y-2 text-left">
                                            {(selectedConfig?.routing?.rules || []).map((rule: any, i: number) => (
                                                <div key={i} className="bg-purple-500/10 border border-purple-500/30 p-4 rounded-2xl group hover:border-purple-500/60 hover:bg-purple-500/20 transition-all shadow-lg">
                                                    <div className="flex justify-between items-start mb-3">
                                                        <div className="min-w-0">
                                                            <div className="text-[12px] font-black text-slate-200 truncate">{rule.ruleTag || `Rule #${i+1}`}</div>
                                                            <div className="inline-block px-3 py-1 rounded-full bg-slate-950 border border-slate-800 text-[10px] text-purple-400 font-black uppercase mt-1.5 shadow-inner">
                                                                ➔ {rule.outboundTag || rule.balancerTag}
                                                            </div>
                                                        </div>
                                                        <div className="flex items-center gap-1.5 opacity-60 group-hover:opacity-100 transition-all translate-x-2 group-hover:translate-x-0">
                                                            <button onClick={() => openSectionJson('rule', 'Rule JSON', rule)} title="JSON" className="p-2 rounded-md bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700"><Icon name="Code" weight="bold" /></button>
                                                            <button onClick={() => importRoutingItem('rules', rule)} title="Импортировать наверх" className="p-2 rounded-md bg-purple-500/20 text-purple-400 hover:bg-purple-500 hover:text-white"><Icon name="ArrowCircleUp" weight="bold" /></button>
                                                        </div>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>

                                    {/* Balancers Section */}
                                    <div className="space-y-4">
                                        <div className="flex items-center gap-4">
                                            <div className="h-px flex-1 bg-gradient-to-r from-amber-500/40 to-transparent"></div>
                                            <h4 className="text-[11px] font-black text-amber-400 uppercase tracking-[0.3em] flex items-center gap-2">
                                                <Icon name="Graph" weight="fill" /> Balancers
                                            </h4>
                                            <div className="h-px flex-1 bg-transparent"></div>
                                        </div>
                                        <div className="space-y-2 text-left">
                                            {(selectedConfig?.routing?.balancers || []).map((bal: any, i: number) => (
                                                <div key={i} className="bg-amber-500/10 border border-amber-500/30 p-4 rounded-2xl flex justify-between items-center group hover:border-amber-500/60 hover:bg-amber-500/20 transition-all shadow-lg">
                                                    <div className="min-w-0">
                                                        <div className="text-[12px] font-black text-amber-500 italic truncate mb-1">{bal.tag}</div>
                                                        <div className="text-[9px] font-bold text-slate-500 uppercase tracking-tighter">STRATEGY: {bal.strategy?.type}</div>
                                                    </div>
                                                    <div className="flex items-center gap-1.5 opacity-60 group-hover:opacity-100 transition-all translate-x-2 group-hover:translate-x-0">
                                                        <button onClick={() => openSectionJson('balancer', 'Balancer JSON', bal)} title="JSON" className="p-2 rounded-md bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700"><Icon name="Code" weight="bold" /></button>
                                                        <button onClick={() => importRoutingItem('balancers', bal)} title="Импортировать балансировщик" className="p-2 rounded-md bg-amber-500/20 text-amber-400 hover:bg-amber-500 hover:text-white"><Icon name="ArrowCircleUp" weight="bold" /></button>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </Modal>
    );
};