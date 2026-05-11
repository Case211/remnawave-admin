// @ts-nocheck
import React from 'react';
import { useInboundEditor } from '../../hooks/useInboundEditor';
import { EditorLayout } from '../ui/EditorLayout';
import { InboundGeneral } from './inbound/InboundGeneral';
import { InboundClients } from './inbound/InboundClients';
import { InboundSniffing } from './inbound/InboundSniffing';
import { InboundTun } from './inbound/InboundTun';
import { TransportSettings } from './shared/TransportSettings';

export const InboundModal = ({ data, onSave, onClose }: any) => {
    const {
        local,
        setLocal,
        updateField,
        handleProtocolChange,
        handleSave,
        rawMode,
        setRawMode,
        errors,
        getError
    } = useInboundEditor(data, onSave);

    return (
        <EditorLayout
            title="Редактор Inbound"
            local={local}
            setLocal={setLocal}
            rawMode={rawMode}
            setRawMode={setRawMode}
            errors={errors}
            onSave={handleSave}
            onClose={onClose}
            schemaMode="inbound"
        >
            <div className="space-y-8 pb-8">
                <section className="relative z-40 animate-in fade-in slide-in-from-top-4 duration-500">
                    <InboundGeneral 
                        inbound={local} 
                        onChange={updateField} 
                        onProtocolChange={handleProtocolChange}
                        errors={{ tag: getError('tag'), port: getError('port') }} 
                    />
                </section>

                <section className="relative z-30">
                    {local.protocol === 'tun' ? (
                        <InboundTun inbound={local} onChange={updateField} />
                    ) : (
                        <InboundClients 
                            inbound={local} 
                            onChange={updateField} 
                            errors={{ clients: getError('clients') }} 
                        />
                    )}
                </section>

                {/* Transport / Stream Settings */}
                <section className="relative z-20">
                    <TransportSettings
                        streamSettings={local.streamSettings}
                        onChange={(s: any) => updateField('streamSettings', s)}
                        isClient={false}
                        protocol={local.protocol}
                    />
                </section>

                <section className="relative z-10 border-t border-slate-800/50 pt-6">
                    <InboundSniffing
                        sniffing={local.sniffing}
                        onChange={updateField}
                    />
                </section>
            </div>
        </EditorLayout>
    );
};
