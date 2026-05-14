// @ts-nocheck
import React, { useState } from 'react';
import { Icon } from '../../ui/Icon';
import { Switch } from '../../ui/Switch';
import { Help } from '../../ui/Help';
import { SockoptEditor } from './SockoptEditor';
import { Select } from '../../ui/Select';

interface XhttpSettingsEditorProps {
    xhttpSettings: any;
    onChange: (newSettings: any) => void;
    isClient?: boolean;
    isDownload?: boolean; // If this is part of downloadSettings
}

export const XhttpSettingsEditor = ({ xhttpSettings = {}, onChange, isClient = false, isDownload = false }: XhttpSettingsEditorProps) => {
    const [showExtra, setShowExtra] = useState(false);
    const [showXmux, setShowXmux] = useState(false);
    const [showDownload, setShowDownload] = useState(false);

    const update = (path: string[], value: any) => {
        const newObj = JSON.parse(JSON.stringify(xhttpSettings));
        let curr = newObj;
        for (let i = 0; i < path.length - 1; i++) {
            if (!curr[path[i]]) curr[path[i]] = {};
            curr = curr[path[i]];
        }
        
        if (value === "" || value === undefined || value === null) {
            delete curr[path[path.length - 1]];
        } else {
            curr[path[path.length - 1]] = value;
        }
        onChange(newObj);
    };

    const extra = xhttpSettings.extra || {};
    const xmux = extra.xmux || {};

    return (
        <div className={`space-y-4 animate-in fade-in ${isDownload ? 'bg-indigo-950/20 p-4 rounded-xl border border-indigo-500/30' : ''}`}>
            {isDownload && (
                <div className="flex items-center gap-2 text-indigo-400 font-bold text-xs uppercase mb-2">
                    <Icon name="DownloadSimple" weight="bold" /> Download-Specific XHTTP Settings
                </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <Select 
                        label="Mode"
                        hint="auto: TLS H2 -> stream-up, Reality -> stream-one, else packet-up. packet-up: Highest compatibility (split uploads). stream-up: Full duplex streaming (recommended for gRPC/CF). stream-one: Single HTTP request for both directions."
                        value={xhttpSettings.mode || "auto"} 
                        onChange={val => update(['mode'], val)}
                        options={[
                            { value: "auto", label: "AUTO", description: "Recommended" },
                            { value: "packet-up", label: "Packet-Up", description: "Highest compatibility" },
                            { value: "stream-up", label: "Stream-Up", description: "Full duplex (Fast)" },
                            { value: "stream-one", label: "Stream-One", description: "Single request" },
                        ]}
                    />
                <div>
                    <label className="label-xs">Path</label>
                    <input className="input-base font-mono" 
                        placeholder="/yourpath" 
                        value={xhttpSettings.path || ""} 
                        onChange={e => update(['path'], e.target.value)} 
                    />
                </div>
                <div className="md:col-span-2">
                    <label className="label-xs flex items-center">Host <Help position="bottom">Override Host header. Priority: host &gt; serverName &gt; address.</Help></label>
                    <input className="input-base font-mono" 
                        placeholder="example.com" 
                        value={xhttpSettings.host || ""} 
                        onChange={e => update(['host'], e.target.value)} 
                    />
                </div>
            </div>

            {/* --- EXTRA SETTINGS --- */}
            <div className="border-t border-slate-800 pt-4">
                <button 
                    onClick={() => setShowExtra(!showExtra)}
                    className="flex items-center gap-2 text-[10px] font-bold uppercase text-slate-400 hover:text-white transition-colors"
                >
                    <Icon name={showExtra ? "CaretDown" : "CaretRight"} />
                    Extra Settings (Headers, Padding, Performance)
                </button>

                {showExtra && (
                    <div className="mt-4 space-y-4 animate-in slide-in-from-top-2">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label className="label-xs flex items-center">Header Padding <Help>Range like "100-1000". Random bytes added to headers to mask length.</Help></label>
                                <input className="input-base font-mono" 
                                    placeholder="100-1000" 
                                    value={extra.xPaddingBytes || ""} 
                                    onChange={e => update(['extra', 'xPaddingBytes'], e.target.value)} 
                                />
                            </div>
                            <div>
                                <label className="label-xs flex items-center">Stream-Up Keep-Alive (s) <Help>Server sends padding every N seconds to keep CF/CDN alive. e.g. "20-80".</Help></label>
                                <input className="input-base font-mono" 
                                    placeholder="20-80" 
                                    value={extra.scStreamUpServerSecs || ""} 
                                    onChange={e => update(['extra', 'scStreamUpServerSecs'], e.target.value)} 
                                />
                            </div>
                        </div>

                        <div className="grid grid-cols-2 gap-4 bg-slate-950 p-3 rounded-lg border border-slate-800">
                            <Switch
                                checked={extra.noGRPCHeader === true}
                                onChange={checked => update(['extra', 'noGRPCHeader'], checked)}
                                label="No gRPC Header"
                            />
                            <Switch
                                checked={extra.noSSEHeader === true}
                                onChange={checked => update(['extra', 'noSSEHeader'], checked)}
                                label="No SSE Header"
                            />
                        </div>

                        {/* Packet-up specific */}
                        <div className="space-y-2">
                            <div className="text-[10px] font-bold text-slate-500 uppercase flex items-center gap-2">
                                <Icon name="Package" /> Packet-Up Mode Settings
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                <div>
                                    <label className="label-xs text-[10px]">Max POST Bytes</label>
                                    <input className="input-base text-xs font-mono" placeholder="1000000"
                                        value={extra.scMaxEachPostBytes || ""} 
                                        onChange={e => update(['extra', 'scMaxEachPostBytes'], e.target.value)} />
                                </div>
                                <div>
                                    <label className="label-xs text-[10px]">Min Post Interval (ms)</label>
                                    <input className="input-base text-xs font-mono" placeholder="30"
                                        value={extra.scMinPostsIntervalMs || ""} 
                                        onChange={e => update(['extra', 'scMinPostsIntervalMs'], e.target.value)} />
                                </div>
                                <div>
                                    <label className="label-xs text-[10px]">Max Buffered Posts</label>
                                    <input type="number" className="input-base text-xs font-mono" placeholder="30"
                                        value={extra.scMaxBufferedPosts || ""} 
                                        onChange={e => update(['extra', 'scMaxBufferedPosts'], parseInt(e.target.value))} />
                                </div>
                            </div>
                        </div>

                        {/* XMUX SETTINGS */}
                        <div className="border-t border-slate-800/50 pt-2">
                            <button 
                                onClick={() => setShowXmux(!showXmux)}
                                className="flex items-center gap-2 text-[10px] font-bold uppercase text-blue-400 hover:text-blue-300 transition-colors"
                            >
                                <Icon name={showXmux ? "CaretDown" : "CaretRight"} />
                                XMUX Control (H2/H3 Multiplexing)
                            </button>

                            {showXmux && (
                                <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mt-4 p-4 bg-blue-900/10 rounded-xl border border-blue-500/20 animate-in slide-in-from-top-1">
                                    <div>
                                        <label className="label-xs flex items-center">Max Concurrency <Help>Concurrent requests per connection. e.g. "16-32".</Help></label>
                                        <input className="input-base font-mono" placeholder="16-32"
                                            value={xmux.maxConcurrency || ""} 
                                            onChange={e => update(['extra', 'xmux', 'maxConcurrency'], e.target.value)} />
                                    </div>
                                    <div>
                                        <label className="label-xs flex items-center">Max Connections <Help>If set, opens new connection for each request until limit.</Help></label>
                                        <input className="input-base font-mono" placeholder="0"
                                            value={xmux.maxConnections || ""} 
                                            onChange={e => update(['extra', 'xmux', 'maxConnections'], e.target.value)} />
                                    </div>
                                    <div>
                                        <label className="label-xs flex items-center">Reuse Times <Help>How many times a connection can be reused.</Help></label>
                                        <input className="input-base font-mono" placeholder="0"
                                            value={xmux.cMaxReuseTimes || ""} 
                                            onChange={e => update(['extra', 'xmux', 'cMaxReuseTimes'], e.target.value)} />
                                    </div>
                                    <div>
                                        <label className="label-xs flex items-center">Max Request Times <Help>Nginx limit is 1000. Core default is "600-900".</Help></label>
                                        <input className="input-base font-mono" placeholder="600-900"
                                            value={xmux.hMaxRequestTimes || ""} 
                                            onChange={e => update(['extra', 'xmux', 'hMaxRequestTimes'], e.target.value)} />
                                    </div>
                                    <div>
                                        <label className="label-xs flex items-center">Max Reusable Secs <Help>Nginx limit is 1h. Core default is "1800-3000".</Help></label>
                                        <input className="input-base font-mono" placeholder="1800-3000"
                                            value={xmux.hMaxReusableSecs || ""} 
                                            onChange={e => update(['extra', 'xmux', 'hMaxReusableSecs'], e.target.value)} />
                                    </div>
                                    <div>
                                        <label className="label-xs flex items-center">Keep-Alive (s) <Help>0 for auto. -1 to disable.</Help></label>
                                        <input type="number" className="input-base font-mono" placeholder="0"
                                            value={xmux.hKeepAlivePeriod || ""} 
                                            onChange={e => update(['extra', 'xmux', 'hKeepAlivePeriod'], parseInt(e.target.value))} />
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>

            {/* --- DOWNLOAD SETTINGS (ASYMMETRIC) --- */}
            {isClient && !isDownload && (
                <div className="border-t border-slate-800 pt-4">
                    <button 
                        onClick={() => setShowDownload(!showDownload)}
                        className="flex items-center gap-2 text-[10px] font-bold uppercase text-purple-400 hover:text-purple-300 transition-colors"
                    >
                        <Icon name={showDownload ? "CaretDown" : "CaretRight"} />
                        Download-Only Settings (Asymmetric Upload/Download)
                    </button>

                    {showDownload && (
                        <div className="mt-4 space-y-4 animate-in slide-in-from-top-2">
                            <div className="bg-purple-900/10 border border-purple-500/20 p-4 rounded-xl space-y-4">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div>
                                        <label className="label-xs">Download Address</label>
                                        <input className="input-base font-mono" placeholder="another-cdn.com or IP"
                                            value={extra.downloadSettings?.address || ""}
                                            onChange={e => update(['extra', 'downloadSettings', 'address'], e.target.value)} />
                                    </div>
                                    <div>
                                        <label className="label-xs">Download Port</label>
                                        <input type="number" className="input-base font-mono" placeholder="443"
                                            value={extra.downloadSettings?.port || ""}
                                            onChange={e => update(['extra', 'downloadSettings', 'port'], parseInt(e.target.value))} />
                                    </div>
                                </div>

                                <div className="p-3 bg-black/20 rounded-lg border border-slate-800 space-y-4">
                                    <div className="flex items-center gap-2 text-[10px] font-bold text-slate-400 uppercase">
                                        <Icon name="ShieldCheck" /> Download Security
                                    </div>
                                    <div className="grid grid-cols-2 gap-4">
                                        <Select 
                                            value={extra.downloadSettings?.security || "tls"}
                                            onChange={val => update(['extra', 'downloadSettings', 'security'], val)}
                                            options={[
                                                { value: "tls", label: "TLS" },
                                                { value: "reality", label: "REALITY" },
                                            ]}
                                            className="w-full"
                                        />
                                        <input className="input-base text-xs font-mono" placeholder="SNI (optional)"
                                            value={extra.downloadSettings?.[extra.downloadSettings?.security === 'reality' ? 'realitySettings' : 'tlsSettings']?.serverName || ""}
                                            onChange={e => update(['extra', 'downloadSettings', extra.downloadSettings?.security === 'reality' ? 'realitySettings' : 'tlsSettings', 'serverName'], e.target.value)} />
                                    </div>
                                </div>

                                {/* Recursive XHTTP settings for download if needed, but usually just path is enough */}
                                <div>
                                    <label className="label-xs">Download Path (must match upload usually)</label>
                                    <input className="input-base font-mono" placeholder="/yourpath"
                                        value={extra.downloadSettings?.xhttpSettings?.path || ""}
                                        onChange={e => update(['extra', 'downloadSettings', 'xhttpSettings', 'path'], e.target.value)} />
                                </div>
                                
                                <div className="bg-slate-900/50 p-2 rounded text-[10px] text-slate-500 italic">
                                    Note: You can further customize downloadSettings JSON for full asymmetric split.
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};
