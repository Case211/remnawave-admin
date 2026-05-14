// @ts-nocheck
import React from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Icon } from '../ui/Icon';
import { JsonEditor } from '../ui/JsonEditor';
import { useTagDetails } from '../../hooks/useTagDetails';

export const TagDetailsModal = ({ 
    tag, 
    customUrl, 
    customFormat, 
    onClose 
}: { 
    tag: string, 
    customUrl?: string, 
    customFormat?: string, 
    onClose: () => void 
}) => {
    const { text, loading, handleCopy } = useTagDetails(tag, customUrl, customFormat);

    return (
        <Modal 
            title={`Details: ${tag}`} 
            onClose={onClose} 
            onSave={onClose} 
            className="max-w-2xl" 
            isSecondary={true}
            extraButtons={<Button variant="secondary" onClick={handleCopy} icon="Копировать">Copy Raw Text</Button>}
        >
            <div className="h-[500px] relative overflow-hidden rounded-xl border border-slate-700 bg-[#1e1e1e]">
                {loading ? (
                    <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-500 bg-slate-900/50 rounded-xl z-10">
                        <Icon name="Spinner" className="animate-spin text-4xl mb-3 text-indigo-500" />
                        <span className="text-xs font-bold uppercase tracking-wider">Extracting records...</span>
                    </div>
                ) : (
                    <div className="h-full w-full">
                        <JsonEditor 
                            value={text} 
                            onChange={() => {}} 
                            readOnly={true} 
                            mode="plaintext" 
                        />
                    </div>
                )}
            </div>
        </Modal>
    );
};