// @ts-nocheck
import React, { useState, useEffect } from 'react';
import { Modal } from '../ui/Modal';
import { JsonField } from '../ui/JsonField';

interface SectionJsonModalProps {
    title: string;
    data: any;
    onClose: () => void;
    onSave: (newData: any) => void;
    schemaMode: any; // Добавили
}

export const SectionJsonModal = ({ title, data, onClose, onSave, schemaMode }: SectionJsonModalProps) => {
    const [localData, setLocalData] = useState(data);

    useEffect(() => {
        setLocalData(data);
    }, [data]);

    return (
        <Modal 
            title={title} 
            onClose={onClose} 
            onSave={() => onSave(localData)}
            className="h-full overflow-hidden"
        >
            <JsonField 
                label="Partial Configuration" 
                value={localData} 
                onChange={setLocalData} 
                className="flex-1" 
                schemaMode={schemaMode} // Передаем сюда
            />
        </Modal>
    );
};