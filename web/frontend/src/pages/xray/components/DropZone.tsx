// @ts-nocheck
import React from 'react';
import { Button } from './ui/Button';
import { Icon } from './ui/Icon';

interface DropZoneProps {
    onFileLoaded: (config: any) => void;
}

export const DropZone = ({ onFileLoaded }: DropZoneProps) => {
    const handleFile = (file: File) => {
        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                onFileLoaded(JSON.parse(e.target?.result as string));
            } catch (err) {
                alert("Invalid JSON");
            }
        };
        reader.readAsText(file);
    };

    const createEmpty = () => {
        onFileLoaded({
            log: { loglevel: "warning" },
            inbounds: [],
            outbounds: [],
            routing: { rules: [], balancers: [] }
        });
    };

    return (
        <div className="h-screen flex flex-col items-center justify-center bg-slate-950 text-slate-400 border-4 border-dashed border-slate-800 m-4 rounded-3xl"
             onDragOver={e => e.preventDefault()}
             onDrop={e => {
                 e.preventDefault();
                 if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
             }}
        >
            <Icon name="FileJson" className="text-8xl mb-4 text-slate-700" />
            <h1 className="text-2xl text-white font-bold mb-2">Xray Config Editor</h1>
            <p className="mb-6">Drop config.json here</p>
            <div className="flex gap-4">
                <label className="bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-2 rounded-lg cursor-pointer font-bold transition-colors flex items-center gap-2">
                    <Icon name="FolderOpen" /> Open File
                    <input type="file" className="hidden" accept=".json"
                           onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])} />
                </label>
                <Button variant="secondary" onClick={createEmpty} icon="PlusCircle">Create Empty</Button>
            </div>
        </div>
    );
};