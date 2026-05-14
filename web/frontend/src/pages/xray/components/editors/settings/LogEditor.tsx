// @ts-nocheck
import React from 'react';
import { Switch } from '../../ui/Switch';
import { Card } from '../../ui/Card';
import { Select } from '../../ui/Select';

export const LogEditor = ({ log, onChange, onToggle }) => {
    const enabled = !!log;
    const localLog = log || { loglevel: "warning" };

    const update = (field: string, val: any) => {
        onChange({ ...localLog, [field]: val });
    };

    return (
        <Card 
            title="Log Configuration" 
            icon="TerminalWindow"
            headerExtra={<Switch checked={enabled} onChange={() => onToggle({ loglevel: "warning" })} />}
        >
            <p className="text-xs text-slate-500 mb-2">System output logs</p>

            {enabled && (
                <div className="animate-in fade-in slide-in-from-top-2 pt-2 border-t border-slate-800/50">
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="md:col-span-2">
                            <Select 
                                label="Log Level"
                                value={localLog.loglevel || "warning"}
                                onChange={val => update('loglevel', val)}
                                options={[
                                    { value: "debug", label: "DEBUG", description: "Most verbose logs" },
                                    { value: "info", label: "INFO", description: "Standard information" },
                                    { value: "warning", label: "WARNING", description: "Default (only issues)" },
                                    { value: "error", label: "ERROR", description: "Only fatal errors" },
                                    { value: "none", label: "NONE", description: "Silent mode" }
                                ]}
                            />
                        </div>
                        <div className="flex items-end pb-3">
                            <Switch 
                                checked={localLog.dnsLog || false}
                                onChange={checked => update('dnsLog', checked)}
                                label="Enable DNS Log"
                            />
                        </div>
                        <div className="col-span-full">
                            <label className="label-xs">Access Log Path</label>
                            <input className="input-base font-mono" 
                                placeholder="/var/log/xray/access.log"
                                value={localLog.access || ""}
                                onChange={e => update('access', e.target.value)}
                            />
                        </div>
                        <div className="col-span-full">
                            <label className="label-xs">Error Log Path</label>
                            <input className="input-base font-mono" 
                                placeholder="/var/log/xray/error.log"
                                value={localLog.error || ""}
                                onChange={e => update('error', e.target.value)}
                            />
                        </div>
                    </div>
                </div>
            )}
        </Card>
    );
};