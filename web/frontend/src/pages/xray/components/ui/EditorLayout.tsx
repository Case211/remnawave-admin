import React from 'react';
import { Modal } from './Modal';
import { Button } from './Button';
import { JsonField } from './JsonField';
import { Icon } from './Icon';

interface EditorLayoutProps {
    title: string;
    local: any;
    setLocal: (data: any) => void;
    rawMode: boolean;
    setRawMode: (val: boolean) => void;
    errors: any[];
    onSave: () => void;
    onClose: () => void;
    schemaMode: any;
    children: React.ReactNode;
    extraButtons?: React.ReactNode;
}

export const EditorLayout = ({
    title,
    local,
    setLocal,
    rawMode,
    setRawMode,
    errors,
    onSave,
    onClose,
    schemaMode,
    children,
    extraButtons
}: EditorLayoutProps) => {
    
    const modalButtons = (
        <div className="flex gap-2">
            {extraButtons}
            <Button
                variant="secondary"
                className="text-xs py-1 px-3"
                onClick={() => setRawMode(!rawMode)}
                icon={rawMode ? "Layout" : "Code"}
            >
                {rawMode ? "UI-режим" : "JSON-режим"}
            </Button>
        </div>
    );

    return (
        <Modal 
            title={rawMode ? `${title} (JSON)` : title} 
            onClose={onClose} 
            onSave={onSave}
            extraButtons={modalButtons}
            className="h-full overflow-hidden"
        >
            {errors.length > 0 && (
                <div className="mb-4 p-3 bg-rose-900/20 border border-rose-500/50 rounded-xl text-rose-200 text-xs animate-in fade-in slide-in-from-top-2 shrink-0">
                    <div className="flex items-center gap-2 mb-1 font-bold">
                        <Icon name="WarningCircle" className="text-rose-500" />
                        Ошибки валидации
                    </div>
                    <ul className="list-disc pl-5 space-y-0.5 opacity-80">
                        {errors.map((err, i) => <li key={i}>{err.message}</li>)}
                    </ul>
                </div>
            )}

            {rawMode ? (
                <div className="flex-1 min-h-0 h-full flex flex-col">
                    <JsonField
                        label="Исходная конфигурация"
                        value={local} 
                        onChange={setLocal} 
                        schemaMode={schemaMode} 
                        className="flex-1" 
                    />
                </div>
            ) : (
                <div className="flex flex-col h-full md:max-h-[60vh] adaptive-height overflow-y-auto custom-scroll p-1 pb-10">
                    {children}
                </div>
            )}
        </Modal>
    );
};
