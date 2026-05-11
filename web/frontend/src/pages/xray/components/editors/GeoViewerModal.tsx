// @ts-nocheck
import React, { useRef, useEffect, useState, useMemo } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Icon } from '../ui/Icon';
import { toast } from 'sonner';
import { JsonEditor } from '../ui/JsonEditor';
import { Select } from '../ui/Select';
import { useGeoViewer } from '../../hooks/useGeoViewer';
import { useTagDetails } from '../../hooks/useTagDetails';
import { VList } from 'virtua';

const CUSTOM_PRESETS = [
    { label: '🌍 V2Fly GeoSite', format: 'geosite', url: 'https://cdn.jsdelivr.net/gh/v2fly/domain-list-community@release/dlc.dat' },
    { label: '🌍 V2Fly GeoIP', format: 'geoip', url: 'https://cdn.jsdelivr.net/gh/v2fly/geoip@release/geoip.dat' },
    { label: '🇷🇺 Zapret (.dat)', format: 'geosite', url: 'https://github.com/kutovoys/ru_gov_zapret/releases/latest/download/zapret.dat' },
    { label: '🇷🇺 Runet GeoSite', format: 'geosite', url: 'https://raw.githubusercontent.com/runetfreedom/russia-v2ray-rules-dat/release/geosite.dat' },
    { label: '🇷🇺 Runet GeoIP', format: 'geoip', url: 'https://raw.githubusercontent.com/runetfreedom/russia-v2ray-rules-dat/release/geoip.dat' },
];

const TagDetailsPanel = ({ tag, customUrl, customFormat, customFileBuffer, onClose }: { tag: string, customUrl?: string, customFormat?: string, customFileBuffer?: ArrayBuffer | null, onClose: () => void }) => {
    const { text, loading, handleCopy } = useTagDetails(tag, customUrl, customFormat, customFileBuffer);

    return (
        <div className="w-full md:w-[400px] lg:w-[550px] shrink-0 flex flex-col bg-slate-900 border border-slate-800 rounded-xl overflow-hidden animate-in slide-in-from-right-8 fade-in duration-200 shadow-2xl h-full">
            <div className="flex items-center justify-between p-3 border-b border-slate-800 bg-slate-900/50 shrink-0">
                <div className="flex items-center gap-2 min-w-0">
                    <Icon name="ListDashes" className="text-indigo-400 shrink-0" />
                    <span className="text-sm font-bold text-slate-200 truncate pr-2">{tag}</span>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                    <button onClick={handleCopy} className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded transition-colors" title="Скопировать текст"><Icon name="Копировать" /></button>
                    <button onClick={onClose} className="p-1.5 text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 rounded transition-colors" title="Закрыть"><Icon name="X" /></button>
                </div>
            </div>
            <div className="flex-1 relative bg-slate-950 p-1 min-h-0 overflow-hidden">
                {loading ? (
                    <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-500">
                        <Icon name="Spinner" className="animate-spin text-3xl mb-3 text-indigo-500" />
                        <span className="text-[10px] font-bold uppercase tracking-wider">Extracting...</span>
                    </div>
                ) : (
                    <div className="h-full w-full overflow-hidden">
                        <JsonEditor
                            value={text}
                            onChange={() => {}}
                            readOnly={true}
                            mode="plaintext"
                        />
                    </div>
                )}
            </div>
        </div>
    );
};

export const GeoViewerModal = ({ onClose }: { onClose: () => void }) => {
    const {
        activeTab,
        handleTabChange,
        customUrl,
        setCustomUrl,
        customFormat,
        setCustomFormat,
        customFileBuffer,
        loading,
        customLoading,
        search,
        setSearch,
        isDeepSearch,
        setIsDeepSearch,
        deepSearchLoading,
        displayData,
        viewTag,
        setViewTag,
        fileInputRef,
        handleFileUpload,
        fetchCustomList
    } = useGeoViewer();

    const handleCopyAll = async () => {
        if (displayData.length === 0) return toast.warning("Nothing to copy");
        const prefix = activeTab === 'geosite' ? 'geosite:' : activeTab === 'geoip' ? 'geoip:' : '';
        const textToCopy = displayData.map(d => `${prefix}${d.code}`).join('\n');
        
        try {
            if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(textToCopy);
            else {
                const ta = document.createElement("textarea");
                ta.value = textToCopy; ta.style.position = "fixed"; ta.style.left = "-999999px";
                document.body.appendChild(ta); ta.focus(); ta.select(); document.execCommand('copy'); ta.remove();
            }
            toast.success(`Copied ${displayData.length} items`);
        } catch { toast.error("Failed to copy data"); }
    };

    const renderItem = (item: any) => {
        const isText = activeTab === 'custom' && customFormat === 'text';
        const isActive = viewTag?.code === item.code;
        return (
            <div 
                key={item.code}
                onClick={() => {
                    if (isText) return;
                    const prefix = activeTab === 'geosite' ? 'geosite:' : activeTab === 'geoip' ? 'geoip:' : customFormat === 'geosite' ? 'geosite:' : 'geoip:';
                    setViewTag({ tag: `${prefix}${item.code}`, code: item.code, url: activeTab === 'custom' ? customUrl : undefined, format: activeTab === 'custom' ? customFormat : undefined });
                }}
                className={`flex justify-between items-center p-2.5 rounded-lg transition-all group ${isText ? 'bg-slate-900 border border-slate-800' : isActive ? 'bg-indigo-900/40 border border-indigo-500 ring-1 ring-indigo-500 shadow-[0_0_15px_rgba(99,102,241,0.2)]' : 'bg-slate-900 border border-slate-800 cursor-pointer hover:border-indigo-500/50 hover:bg-slate-800/80'}`}
            >
                <span className={`font-mono text-[11px] truncate pr-2 transition-colors ${isActive ? 'text-white font-bold' : 'text-slate-200 group-hover:text-white'}`} title={item.code}>{item.code}</span>
                {!isText && (
                    <span className={`text-[10px] px-1.5 py-0.5 rounded shrink-0 border transition-colors ${isActive ? 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30' : 'bg-slate-950 text-slate-500 border-transparent group-hover:border-indigo-500/50 group-hover:text-indigo-300'}`}>{item.count}</span>
                )}
            </div>
        );
    };

    // Virtualization grid logic: chunk data into rows of 5
    const chunkedRows = useMemo(() => {
        const rows = [];
        for (let i = 0; i < displayData.length; i += 5) {
            rows.push(displayData.slice(i, i + 5));
        }
        return rows;
    }, [displayData]);

    return (
        <Modal title="Просмотр Geo-данных" onClose={onClose} onSave={onClose} className="max-w-7xl"
            extraButtons={
                <div className="flex bg-slate-950 p-1 rounded-xl border border-slate-800 shrink-0 h-11 items-center">
                    <button onClick={() => handleTabChange('geosite')} className={`px-4 h-full text-xs font-bold rounded-lg transition-all ${activeTab === 'geosite' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'}`}>GeoSite</button>
                    <button onClick={() => handleTabChange('geoip')} className={`px-4 h-full text-xs font-bold rounded-lg transition-all ${activeTab === 'geoip' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'}`}>GeoIP</button>
                    <button onClick={() => handleTabChange('custom')} className={`px-4 h-full text-xs font-bold rounded-lg transition-all ${activeTab === 'custom' ? 'bg-emerald-600 text-white' : 'text-slate-400 hover:text-white'}`}>Custom Source</button>
                </div>
            }
        >
            <div className="h-[80vh] flex flex-col gap-4 relative">
                
                {activeTab === 'custom' && (
                    <div className="flex flex-col gap-3 bg-slate-900 p-3 rounded-xl border border-slate-800 shrink-0 animate-in fade-in slide-in-from-top-2">
                        <div className="flex flex-wrap items-center gap-2 border-b border-slate-800 pb-2">
                            <span className="text-[10px] text-slate-500 uppercase tracking-wider font-bold mr-1">Quick Presets:</span>
                            {CUSTOM_PRESETS.map((p, i) => (
                                <button key={i} onClick={() => { setCustomUrl(p.url); setCustomFormat(p.format as any); }} className="px-2.5 py-1 text-[10px] font-bold bg-slate-950 border border-slate-700 text-slate-300 rounded hover:border-indigo-500 hover:bg-indigo-600/10 hover:text-indigo-300 transition-colors">
                                    {p.label}
                                </button>
                            ))}
                        </div>

                        <div className="flex flex-col md:flex-row gap-2">
                            <Select 
                                value={customFormat} 
                                onChange={val => setCustomFormat(val as any)}
                                options={[
                                    { value: "geoip", label: "GeoIP (.dat)" },
                                    { value: "geosite", label: "GeoSite (.dat)" },
                                    { value: "text", label: "Raw Text (.txt)" },
                                ]}
                                className="w-full md:w-48"
                            />
                            
                            <div className="flex-1 flex gap-2">
                                <div className="flex-1 relative h-11">
                                    <Icon name="Link" className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                                    <input className="w-full h-full bg-slate-950 border border-slate-700 rounded-lg pl-9 pr-3 text-sm text-white focus:border-emerald-500 outline-none transition-colors font-mono" placeholder="Paste URL or select local file..." value={customUrl} onChange={e => setCustomUrl(e.target.value)} onKeyDown={e => e.key === 'Enter' && fetchCustomList()} />
                                </div>
                                
                                <input type="file" ref={fileInputRef} className="hidden" accept=".dat,.txt" onChange={handleFileUpload} />
                                <Button variant="secondary" onClick={() => fileInputRef.current?.click()} className="shrink-0 h-11 w-11 p-0" title="Загрузить файл">
                                    <Icon name="UploadSimple" />
                                </Button>
                            </div>

                            <Button variant="success" onClick={fetchCustomList} disabled={customLoading} className="h-11 px-6">
                                {customLoading ? <Icon name="Spinner" className="animate-spin" /> : <Icon name="DownloadSimple" />}
                                <span className="hidden md:inline">Fetch</span>
                            </Button>
                        </div>
                    </div>
                )}

                <div className="flex flex-col md:flex-row gap-3 items-center bg-slate-900 p-3 rounded-xl border border-slate-800 shrink-0">
                    <div className="flex-1 relative w-full flex items-center gap-2">
                        <div className="relative flex-1 h-11">
                            <Icon name="MagnifyingGlass" className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                            <input 
                                className="w-full h-full bg-slate-950 border border-slate-700 rounded-lg pl-9 pr-9 text-sm text-white focus:border-indigo-500 outline-none transition-colors" 
                                placeholder={isDeepSearch ? "Search INSIDE domains/IPs..." : `Search in ${activeTab} categories...`} 
                                value={search} 
                                onChange={e => setSearch(e.target.value)} 
                            />
                            {deepSearchLoading && <Icon name="Spinner" className="absolute right-3 top-1/2 -translate-y-1/2 text-indigo-500 animate-spin" />}
                        </div>
                        {activeTab !== 'custom' || customFormat !== 'text' ? (
                            <button 
                                onClick={() => setIsDeepSearch(!isDeepSearch)}
                                className={`px-4 h-11 text-xs font-bold rounded-lg border transition-all flex items-center gap-2 shrink-0 ${isDeepSearch ? 'bg-indigo-600/20 border-indigo-500 text-indigo-300' : 'bg-slate-950 border-slate-700 text-slate-400 hover:border-slate-500 hover:bg-slate-900'}`}
                                title="Search inside domains/IPs instead of category names"
                            >
                                Deep Search
                            </button>
                        ) : null}
                    </div>
                    <div className="flex items-center gap-3 w-full md:w-auto justify-between h-11">
                        <div className="text-xs text-slate-400 font-mono bg-slate-950 px-4 h-full flex items-center rounded-lg border border-slate-800">
                            Showing: <span className="text-white font-bold ml-1">{displayData.length}</span>
                        </div>
                        <Button variant="secondary" onClick={handleCopyAll} icon="Копировать" className="h-full px-4">Copy All</Button>
                    </div>
                </div>

                <div className="flex-1 flex gap-4 min-h-0 overflow-hidden">
                    <div className="flex-1 bg-slate-950 rounded-xl border border-slate-800 relative min-w-0">
                        {loading && activeTab !== 'custom' ? (
                            <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-500 z-10 bg-slate-950/50 backdrop-blur-sm">
                                <Icon name="Spinner" className="text-4xl animate-spin mb-4 text-indigo-500" />
                                <p className="font-bold tracking-widest text-[10px] uppercase">Validating Database...</p>
                            </div>
                        ) : displayData.length === 0 ? (
                            <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-600">
                                <Icon name="Database" className="text-6xl mb-4 opacity-10" />
                                <p className="text-sm">{isDeepSearch ? "No matching domains/IPs found." : "No items found."}</p>
                            </div>
                        ) : (
                            <VList className="h-full w-full custom-scroll" style={{ overflowY: 'auto' }}>
                                {chunkedRows.map((row, rowIdx) => (
                                    <div key={rowIdx} className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5 gap-2 p-2">
                                        {row.map(item => renderItem(item))}
                                    </div>
                                ))}
                            </VList>
                        )}
                    </div>

                    {viewTag && <TagDetailsPanel tag={viewTag.tag} customUrl={viewTag.url} customFormat={viewTag.format} customFileBuffer={customFileBuffer} onClose={() => setViewTag(null)} />}
                </div>
            </div>
        </Modal>
    );
};