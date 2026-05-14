// @ts-nocheck
import React from 'react';
import { TagSelector } from '../../ui/TagSelector';
import { Switch } from '../../ui/Switch';
import { Card } from '../../ui/Card';
import { Select } from '../../ui/Select';

export const BurstObservatoryEditor = ({ burstObservatory, onChange, onToggle, outboundTags }: any) => {
    const enabled = !!burstObservatory;
    const localObs = burstObservatory || { 
        subjectSelector: [], 
        pingConfig: { destination: "https://connectivitycheck.gstatic.com/generate_204", interval: "1m", sampling: 10 } 
    };

    const update = (field: string, val: any) => {
        onChange({ ...localObs, [field]: val });
    };

    const updatePing = (field: string, val: any) => {
        onChange({ ...localObs, pingConfig: { ...(localObs.pingConfig || {}), [field]: val } });
    };

    return (
        <Card 
            title="Burst Observatory" 
            icon="Lightning"
            headerExtra={
                <Switch 
                    checked={enabled}
                    onChange={() => onToggle({ 
                        subjectSelector: [], 
                        pingConfig: { destination: "https://connectivitycheck.gstatic.com/generate_204", interval: "1m", sampling: 10 } 
                    })}
                />
            }
        >
            <p className="text-xs text-slate-500 -mt-2">Advanced stealth health checks for balancers</p>

            {enabled && (
                <div className="animate-in fade-in slide-in-from-top-2 space-y-4 pt-2">
                    <div className="grid grid-cols-2 gap-4">
                        <div className="col-span-2">
                            <label className="label-xs">Destination URL</label>
                            <input className="input-base font-mono text-xs" 
                                value={localObs.pingConfig?.destination || ""} 
                                onChange={e => updatePing('destination', e.target.value)}
                            />
                        </div>
                        <div className="col-span-2">
                            <label className="label-xs">Connectivity Check URL (Optional)</label>
                            <input className="input-base font-mono text-xs" 
                                placeholder="e.g. https://connectivitycheck.gstatic.com/generate_204"
                                value={localObs.pingConfig?.connectivity || ""} 
                                onChange={e => updatePing('connectivity', e.target.value)}
                            />
                        </div>
                        <div>
                            <label className="label-xs">Interval</label>
                            <input className="input-base font-mono" 
                                placeholder="1m, 30s"
                                value={localObs.pingConfig?.interval || ""} 
                                onChange={e => updatePing('interval', e.target.value)}
                            />
                        </div>
                        <div>
                            <label className="label-xs">Timeout</label>
                            <input className="input-base font-mono" 
                                placeholder="5s"
                                value={localObs.pingConfig?.timeout || ""} 
                                onChange={e => updatePing('timeout', e.target.value)}
                            />
                        </div>
                        <div>
                            <label className="label-xs">Sampling Count</label>
                            <input type="number" className="input-base font-mono" 
                                value={localObs.pingConfig?.sampling || 10} 
                                onChange={e => updatePing('sampling', parseInt(e.target.value))}
                            />
                        </div>
                            <Select 
                                label="HTTP Method"
                                value={localObs.pingConfig?.httpMethod || "HEAD"} 
                                onChange={val => updatePing('httpMethod', val)}
                                options={[
                                    { value: "HEAD", label: "HEAD" },
                                    { value: "GET", label: "GET" },
                                    { value: "POST", label: "POST" },
                                ]}
                            />
                    </div>

                    <div>
                        <TagSelector 
                            label="Subject Selector (Outbounds to Watch)"
                            availableTags={outboundTags}
                            selected={localObs.subjectSelector || []}
                            onChange={v => update('subjectSelector', v)}
                            multi={true}
                            placeholder="Prefix matching..."
                        />
                    </div>
                </div>
            )}
        </Card>
    );
};