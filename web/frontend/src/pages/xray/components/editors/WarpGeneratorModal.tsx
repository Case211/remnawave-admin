// @ts-nocheck
import React, { useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Icon } from '../ui/Icon';
import { Select } from '../ui/Select';
import { toast } from 'sonner';
import { generateWarpAccount } from '../../core/generators/warp';
import { useConfigStore } from '../../store/configStore';
import { getPresets } from '../../core/presets';

interface WarpGeneratorModalProps {
    onClose: () => void;
    onGenerate: (outbound: any) => void;
}

export const WarpGeneratorModal = ({ onClose, onGenerate }: WarpGeneratorModalProps) => {
    const { warpWorkerUrl } = useConfigStore();
    const [loading, setLoading] = useState(false);
    const [presetType, setPresetType] = useState('standard');
    const [excludeLocal, setExcludeLocal] = useState(true);

    const handleGenerate = async () => {
        setLoading(true);
        try {
            // 1. Generate WARP account
            const warp = await generateWarpAccount(warpWorkerUrl);

            // 2. Fetch templates
            const allPresets = getPresets();
            let baseOutbound: any;

            if (presetType === 'standard') {
                baseOutbound = {
                    tag: `profile-a-${Math.floor(Math.random() * 1000)}`,
                    protocol: 'wireguard',
                    settings: {
                        secretKey: '',
                        address: [],
                        mtu: 1280,
                        reserved: [0, 0, 0],
                        peers: [{ endpoint: '', publicKey: '', keepAlive: 15, allowedIPs: ['0.0.0.0/0', '::/0'] }]
                    },
                    streamSettings: { network: 'udp' }
                };
            } else {
                const targetPresetName = 
                    presetType === 'awgm1' ? 'WARP Profile A' :
                    presetType === 'awgm2' ? 'WARP Profile B' :
                    presetType === 'awgm3' ? 'WARP Profile C' : '';

                const preset = allPresets.find(p => p.name === targetPresetName);
                if (!preset || !preset.config.outbounds || preset.config.outbounds.length === 0) {
                    console.error("Mismatched target:", targetPresetName, "Available:", allPresets.map(p => p.name));
                    throw new Error(`Internal lookup failed for "${targetPresetName}"`);
                }
                
                // Clone the outbound from preset to avoid mutations
                const originalOb = preset.config.outbounds.find(o => o.protocol === 'wireguard');
                if (!originalOb) throw new Error("WireGuard outbound not found in preset");
                
                baseOutbound = JSON.parse(JSON.stringify(originalOb));
            }

            if (!baseOutbound) throw new Error("Base outbound generation failed");

            // Ensure settings exists
            if (!baseOutbound.settings) baseOutbound.settings = {};
            if (!baseOutbound.settings.peers) baseOutbound.settings.peers = [{}];

            // 3. Merge data
            baseOutbound.settings.secretKey = warp.privateKey;
            baseOutbound.settings.address = [`${warp.ipv4}/32`, `${warp.ipv6}/128`];
            baseOutbound.settings.reserved = warp.reserved;
            baseOutbound.settings.peers[0].endpoint = warp.endpoint;
            baseOutbound.settings.peers[0].publicKey = warp.peerPublicKey;
            
            // 4. Allowed IPs logic
            if (excludeLocal) {
                baseOutbound.settings.peers[0].allowedIPs = [
                    "0.0.0.0/5", "8.0.0.0/7", "11.0.0.0/8", "12.0.0.0/6", "16.0.0.0/4", "32.0.0.0/3", 
                    "64.0.0.0/2", "128.0.0.0/3", "160.0.0.0/5", "168.0.0.0/6", "172.0.0.0/12", 
                    "172.32.0.0/11", "172.64.0.0/10", "172.128.0.0/9", "173.0.0.0/8", "174.0.0.0/7", 
                    "176.0.0.0/4", "192.0.0.0/9", "192.64.0.0/10", "192.128.0.0/11", "192.160.0.0/13", 
                    "192.169.0.0/16", "192.170.0.0/15", "192.172.0.0/14", "192.176.0.0/12", 
                    "192.192.0.0/10", "193.0.0.0/8", "194.0.0.0/7", "196.0.0.0/6", "200.0.0.0/5", 
                    "208.0.0.0/4", "::/0"
                ];
            } else {
                baseOutbound.settings.peers[0].allowedIPs = ["0.0.0.0/0", "::/0"];
            }

            // Generate a unique tag
            const prefix = presetType === 'standard' ? 'cloud' : (presetType.startsWith('awg') ? presetType : 'profile');
            baseOutbound.tag = `${prefix}-${Math.floor(Math.random() * 1000)}`;

            onGenerate(baseOutbound);
            toast.success("Outbound profile generated successfully");
            onClose();

        } catch (e: any) {
            console.error(e);
            toast.error("Generation failed", {
                description: e.message || "Network error or proxy timeout."
            });
        } finally {
            setLoading(false);
        }
    };

    return (
        <Modal title="Generate WARP(WG) Outbound" onClose={onClose} onSave={onClose} extraButtons={null} className="max-w-md">
            <div className="space-y-8 py-2">
                <div className="p-4 bg-indigo-900/10 border border-indigo-500/20 rounded-xl flex items-start gap-3">
                    <Icon name="Lightning" className="text-amber-400 text-xl shrink-0 mt-0.5" weight="fill" />
                    <div className="text-[11px] text-indigo-200 leading-relaxed">
                        This tool registers a new Cloudflare WARP account and generates a pre-configured WireGuard outbound profile.
                    </div>
                </div>

                <div className="space-y-6">
                    <Select 
                        label="WARP Configuration Profile"
                        hint="Choose a profile based on your network. Profiles A-C use advanced obfuscation (AmneziaWG/Finalmask)."
                        value={presetType}
                        onChange={val => setPresetType(val)}
                        options={[
                            { value: 'standard', label: 'Standard WARP (Direct)' },
                            { value: 'awgm1', label: 'WARP Profile A (Optimized)' },
                            { value: 'awgm2', label: 'WARP Profile B (Optimized Alt)' },
                            { value: 'awgm3', label: 'WARP Profile C (Aggressive)' },
                        ]}
                    />

                    <div className="flex items-center justify-between p-3 bg-slate-900/50 rounded-xl border border-slate-800">
                        <div className="flex flex-col">
                            <span className="text-xs font-bold text-slate-200">Exclude Local Traffic</span>
                            <span className="text-[10px] text-slate-500">Bypass local networks (192.168.x.x, etc.)</span>
                        </div>
                        <input 
                            type="checkbox" 
                            className="w-5 h-5 rounded border-slate-700 bg-slate-800 text-indigo-600 focus:ring-indigo-500 cursor-pointer"
                            checked={excludeLocal}
                            onChange={e => setExcludeLocal(e.target.checked)}
                        />
                    </div>
                </div>

                <div className="pt-6 border-t border-slate-800 flex flex-col gap-3">
                    <Button variant="success" icon={loading ? "CircleNotch" : "Lightning"} className={`w-full py-3 h-12 text-sm font-bold ${loading ? "animate-pulse" : ""}`} onClick={handleGenerate} disabled={loading}>
                        {loading ? "Registering WARP..." : "Generate & Add Outbound"}
                    </Button>
                    <Button variant="secondary" className="w-full py-2 text-xs" onClick={onClose} disabled={loading}>Cancel</Button>
                </div>
            </div>
        </Modal>
    );
};
