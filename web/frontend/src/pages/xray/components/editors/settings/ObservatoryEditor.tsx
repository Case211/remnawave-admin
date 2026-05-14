// @ts-nocheck
import React from 'react';
import { TagSelector } from '../../ui/TagSelector';
import { Switch } from '../../ui/Switch';
import { Card } from '../../ui/Card';

export const ObservatoryEditor = ({ observatory, onChange, onToggle, outboundTags }) => {
    const enabled = !!observatory;
    const localObs = observatory || { 
        subjectSelector: [], 
        probeUrl: "https://www.google.com/generate_204", 
        probeInterval: "1m" 
    };

    const update = (field: string, val: any) => {
        onChange({ ...localObs, [field]: val });
    };

    return (
        <Card 
            title="Observatory" 
            icon="Eye"
            headerExtra={
                <Switch 
                    checked={enabled}
                    onChange={() => onToggle({ 
                        subjectSelector: [], 
                        probeUrl: "https://www.google.com/generate_204", 
                        probeInterval: "1m" 
                    })}
                />
            }
        >
            <p className="text-xs text-slate-500 -mt-2">Health checks for Load Balancers</p>

            {enabled && (
                <div className="animate-in fade-in slide-in-from-top-2 space-y-4 pt-2">
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="label-xs">Probe URL</label>
                            <input className="input-base font-mono" 
                                value={localObs.probeUrl || ""} 
                                onChange={e => update('probeUrl', e.target.value)}
                            />
                        </div>
                        <div>
                            <label className="label-xs">Interval</label>
                            <input className="input-base" 
                                placeholder="1m, 30s"
                                value={localObs.probeInterval || ""} 
                                onChange={e => update('probeInterval', e.target.value)}
                            />
                        </div>
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
                        <p className="text-[10px] text-slate-500 mt-2">
                            Select Outbound tags (or prefixes) that will be monitored by Observatory. 
                            Needed for <code>leastPing</code> balancers.
                        </p>
                    </div>
                </div>
            )}
        </Card>
    );
};