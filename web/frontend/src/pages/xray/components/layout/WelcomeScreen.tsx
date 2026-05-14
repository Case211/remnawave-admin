import React from 'react';
import { Icon } from '../ui';
import type { Preset } from '../../core/presets';

interface WelcomeScreenProps {
    presets: Preset[];
    onSelectPreset: (config: any) => void;
    onFileUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
    onOpenRemnawave: () => void;
}

/**
 * Landing screen shown when no config is loaded.
 * Displays preset templates and import options.
 */
export const WelcomeScreen = ({
    presets,
    onSelectPreset,
    onFileUpload,
    onOpenRemnawave,
}: WelcomeScreenProps) => (
    <div className="flex-1 flex flex-col items-center justify-center overflow-y-auto custom-scroll">
        <div className="text-center mb-10">
            <h1 className="text-3xl md:text-4xl text-white font-bold mb-3 tracking-tight">
                Редактор Xray-конфигов
            </h1>
            <p className="text-slate-400 max-w-md mx-auto">
                Перетащи свой <code>config.json</code> в любое место или выбери шаблон для старта.
            </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 w-full max-w-4xl px-4">
            {presets.map((preset, i) => (
                <div
                    key={i}
                    onClick={() => onSelectPreset(preset.config)}
                    className="bg-slate-900/50 hover:bg-slate-800 border border-slate-800 hover:border-indigo-500/50 rounded-xl p-6 cursor-pointer transition-all group shadow-lg hover:shadow-indigo-500/10 flex flex-col gap-3"
                >
                    <div className="bg-slate-950 w-12 h-12 rounded-lg flex items-center justify-center border border-slate-800 group-hover:border-indigo-500/50 group-hover:text-indigo-400 transition-colors">
                        <Icon name={preset.icon} className="text-2xl" weight="duotone" />
                    </div>
                    <div>
                        <h3 className="font-bold text-slate-200 group-hover:text-white mb-1">
                            {preset.name}
                        </h3>
                        <p className="text-xs text-slate-500 leading-relaxed">{preset.description}</p>
                    </div>
                </div>
            ))}
        </div>

        <div className="mt-12 flex flex-col items-center gap-4 opacity-70 hover:opacity-100 transition-opacity pb-8">
            <div className="text-sm text-slate-500">Или загрузить из источника:</div>
            <div className="flex gap-4">
                <label className="text-sm text-slate-400 cursor-pointer flex items-center gap-2 hover:text-indigo-400 transition-colors bg-slate-900 border border-slate-800 px-4 py-2 rounded-full">
                    <Icon name="FolderOpen" /> Локальный файл
                    <input type="file" className="hidden" accept=".json" onChange={onFileUpload} />
                </label>
                <button
                    onClick={onOpenRemnawave}
                    className="text-sm text-slate-400 cursor-pointer flex items-center gap-2 hover:text-indigo-400 transition-colors bg-slate-900 border border-slate-800 px-4 py-2 rounded-full"
                >
                    <Icon name="Cloud" /> Профиль Remnawave
                </button>
            </div>
        </div>
    </div>
);
