// @ts-nocheck
import React, { useState, useEffect } from 'react';
import { Modal } from '../../ui/Modal';
import { Button } from '../../ui/Button';
import { Icon } from '../../ui/Icon';
import { useConfigStore } from '../../../store/configStore';
import { parseXrayLink, parseJsonSubscription } from '../../../utils/link-parser';
import { generateXrayLink } from '../../../utils/link-generator';
import { generateUUID } from '../../../core/generators/crypto';
import { toast } from 'sonner';

// Ключ для хранения HWID
const HWID_STORAGE_KEY = 'xray_editor_v2_hwid';

export const BatchOutboundModal = ({ onClose }: { onClose: () => void }) => {
    const { config, addOutbounds } = useConfigStore();
    const [mode, setMode] = useState<'import' | 'export'>('import');
    const [text, setText] = useState("");
    
    // Подписка
    const [subUrl, setSubUrl] = useState("");
    const [isFetching, setIsFetching] = useState(false);
    
    // Advanced Headers
    const [showAdvanced, setShowAdvanced] = useState(false);
    const [customUA, setCustomUA] = useState("v2rayNG/1.8.5");
    
    // Состояние HWID
    const [customClientId, setCustomClientId] = useState(() => {
        const saved = localStorage.getItem(HWID_STORAGE_KEY);
        if (saved) return saved;
        // Если нет сохраненного - генерим новый
        const newId = generateUUID();
        localStorage.setItem(HWID_STORAGE_KEY, newId);
        return newId;
    });

    useEffect(() => {
        if (mode === 'export') {
            const links: string[] = [];
            config?.outbounds?.forEach((ob: any) => {
                const link = generateXrayLink(ob);
                if (link) links.push(link);
            });
            setText(links.join('\n'));
        }
    }, [mode, config]);

const handleFetchSub = async () => {
    if (!subUrl.trim()) return toast.error("Please enter a subscription URL");
    setIsFetching(true);
    try {
        const targetUrl = subUrl.trim();
        const proxyUrl = `https://crs.bropines.workers.dev/${targetUrl}`;
        
        const headers: Record<string, string> = {
            "x-custom-user-agent": customUA || "v2rayNG/1.8.5",
            "x-hwid": customClientId // Передаем HWID согласно докам Remnawave
        };

        let res = await fetch(proxyUrl, { headers });

        if (!res.ok) throw new Error(`Server returned ${res.status}`);

        // Проверяем заголовки Remnawave на превышение лимита HWID
        if (res.headers.get('x-hwid-max-devices-reached') === 'true' || res.headers.get('x-hwid-limit') === 'true') {
            toast.error("Panel rejected this device (HWID)", { 
                description: "Device limit reached. Check 'Active Devices' in the panel." 
            });
            setIsFetching(false);
            return;
        }

        const rawText = await res.text();
        let decoded = rawText.trim();

        if (!decoded.includes('://')) {
            try {
                let b64 = decoded.replace(/\s/g, '');
                while (b64.length % 4 !== 0) b64 += '=';
                decoded = atob(b64);
                try { decoded = decodeURIComponent(escape(decoded)); } catch (e) {}
            } catch (e) {
                decoded = rawText.trim();
            }
        }

        if (decoded.includes('://')) {
            setText(prev => prev ? prev + '\n\n' + decoded : decoded);
            toast.success("Subscription fetched successfully");
        } else if (decoded.startsWith('[') || decoded.startsWith('{')) {
            // Пробуем распарсить JSON подписку и превратить её обратно в ссылки для удобства отображения/редактирования
            const obs = parseJsonSubscription(decoded);
            if (obs.length > 0) {
                const links = obs.map(o => generateXrayLink(o)).filter(Boolean);
                if (links.length > 0) {
                    setText(prev => prev ? prev + '\n\n' + links.join('\n') : links.join('\n'));
                    toast.success(`Imported ${links.length} nodes from JSON subscription`);
                } else {
                    // Если ссылки не сгенерились (странные протоколы), просто вставляем сырой JSON
                    setText(prev => prev ? prev + '\n\n' + decoded : decoded);
                    toast.success("JSON subscription fetched (Raw)");
                }
            } else {
                toast.error("JSON detected but no valid outbounds found inside");
            }
        } else {
            toast.error("No valid links found in response");
        }
    } catch (err: any) {
        toast.error("Fetch failed", { description: err.message });
    } finally {
        setIsFetching(false);
    }
};

    const regenerateHwid = () => {
        if (confirm("Regenerate HWID? The panel will see this as a NEW device.")) {
            const newId = generateUUID();
            setCustomClientId(newId);
            localStorage.setItem(HWID_STORAGE_KEY, newId);
            toast.info("New HWID generated and saved");
        }
    };

    return (
        <Modal title="Batch Operations" onClose={onClose} className="max-w-2xl" onSave={onClose}>
            <div className="space-y-4">
                <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800">
                    <button onClick={() => setMode('import')} className={`flex-1 py-1.5 text-xs font-bold rounded transition-all ${mode === 'import' ? 'bg-indigo-600 text-white shadow' : 'text-slate-500 hover:text-white'}`}>Import</button>
                    <button onClick={() => setMode('export')} className={`flex-1 py-1.5 text-xs font-bold rounded transition-all ${mode === 'export' ? 'bg-emerald-600 text-white shadow' : 'text-slate-500 hover:text-white'}`}>Export</button>
                </div>

                {mode === 'import' && (
                    <div className="space-y-2 bg-slate-900/50 p-3 rounded-xl border border-slate-800 animate-in fade-in">
                        <div className="flex flex-col sm:flex-row gap-2">
                            <div className="relative flex-1">
                                <Icon name="Link" className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                                <input className="w-full bg-slate-950 border border-slate-700 rounded-lg pl-9 pr-3 py-2 text-sm text-white focus:border-indigo-500 outline-none transition-colors" placeholder="URL подписки..." value={subUrl} onChange={e => setSubUrl(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleFetchSub()}/>
                            </div>
                            <Button variant="secondary" onClick={handleFetchSub} disabled={isFetching || !subUrl}>
                                {isFetching ? <Icon name="Spinner" className="animate-spin" /> : <Icon name="CloudArrowDown" />}
                                Fetch
                            </Button>
                        </div>
                        
                        <div className="flex justify-between items-center px-1">
                            <button onClick={() => setShowAdvanced(!showAdvanced)} className="text-[10px] text-slate-500 hover:text-indigo-400 flex items-center gap-1 uppercase font-bold transition-colors">
                                <Icon name={showAdvanced ? "CaretUp" : "CaretDown"} /> 
                                {showAdvanced ? "Hide Details" : "Device Info (HWID)"}
                            </button>
                            {showAdvanced && (
                                <button onClick={regenerateHwid} className="text-[10px] text-rose-400 hover:text-rose-300 flex items-center gap-1 font-bold transition-colors">
                                    <Icon name="ArrowsClockwise" /> Reset Device ID
                                </button>
                            )}
                        </div>

                        {showAdvanced && (
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 animate-in slide-in-from-top-2">
                                <div>
                                    <label className="text-[9px] uppercase text-slate-500 font-bold mb-1 block font-mono">User-Agent (Fake Client)</label>
                                    <input className="w-full bg-slate-950 border border-slate-800 rounded p-1.5 text-[11px] text-white font-mono" value={customUA} onChange={e => setCustomUA(e.target.value)} />
                                </div>
                                <div>
                                    <label className="text-[9px] uppercase text-slate-500 font-bold mb-1 block font-mono">X-HW-ID (Persistent)</label>
                                    <input className="w-full bg-slate-950 border border-slate-800 rounded p-1.5 text-[11px] text-indigo-300 font-mono" value={customClientId} onChange={e => {
                                        setCustomClientId(e.target.value);
                                        localStorage.setItem(HWID_STORAGE_KEY, e.target.value);
                                    }} />
                                </div>
                            </div>
                        )}
                    </div>
                )}

                <textarea className={`w-full bg-slate-950 border border-slate-700 rounded-lg p-4 text-xs font-mono text-white focus:border-indigo-500 outline-none resize-none leading-relaxed custom-scroll ${mode === 'import' ? 'h-[280px]' : 'h-[380px]'}`} placeholder="Ноды появятся после загрузки или вставки ссылок..." value={text} onChange={e => setText(e.target.value)} readOnly={mode === 'export'} />
                
                {mode === 'import' && text.trim() && (
                    <Button className="w-full" onClick={() => {
                        let obs: any[] = [];
                        
                        // Сначала пробуем построчный парсинг ссылок
                        const lines = text.split(/\n/).filter(l => l.trim());
                        obs = lines.map(l => parseXrayLink(l.trim())).filter(Boolean);
                        
                        // Если ничего не вышло, пробуем распарсить весь текст как JSON-подписку
                        if (obs.length === 0) {
                            obs = parseJsonSubscription(text);
                        }

                        if (obs.length > 0) {
                            addOutbounds(obs);
                            toast.success(`Imported ${obs.length} nodes`);
                            onClose();
                        } else {
                            toast.error("No valid links or JSON configs found to import");
                        }
                    }}>Save To Config</Button>
                )}
            </div>
        </Modal>
    );
};