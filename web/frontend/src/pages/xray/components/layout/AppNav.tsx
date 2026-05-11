import React from 'react';
import { Icon } from '../ui';
import { Button } from '../ui';

interface AppNavProps {
    /** Whether Remnawave panel is connected */
    connected: boolean;
    /** Active push button stage */
    pushStage: 'idle' | 'confirm';
    /** Number of critical diagnostic errors */
    criticalCount: number;
    /** Number of warnings */
    warningCount: number;
    onOpenDiagnostics: () => void;
    onOpenRemnawave: () => void;
    onOpenSwitchProfile: () => void;
    onPush: () => void;
    onDisconnect: () => void;
    onOpenAbout: () => void;
    onFileUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
    onDownload: () => void;
    hasConfig: boolean;
    /** Optional "back to admin" callback shown as a chevron-left button on the left. */
    onBack?: () => void;
}

/**
 * Top navigation bar.
 */
export const AppNav = ({
    connected,
    pushStage,
    criticalCount,
    warningCount,
    onOpenDiagnostics,
    onOpenRemnawave,
    onOpenSwitchProfile,
    onPush,
    onDisconnect,
    onOpenAbout,
    onFileUpload,
    onDownload,
    hasConfig,
    onBack,
}: AppNavProps) => (
    <nav className="h-14 shrink-0 z-40 bg-slate-900/80 backdrop-blur-xl border-b border-slate-800/50 px-4 shadow-2xl flex items-center justify-between">
        {/* Left: Logo + Status */}
        <div className="flex items-center gap-3 min-w-0">
            {onBack && (
                <button
                    type="button"
                    onClick={onBack}
                    className="shrink-0 p-2 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800/60 transition-colors"
                    title="Назад в админку"
                    aria-label="Назад в админку"
                >
                    <Icon name="ArrowLeft" weight="bold" className="text-lg" />
                </button>
            )}
            <div className="bg-gradient-to-br from-indigo-500 to-purple-600 p-2 rounded-xl text-white shadow-lg shadow-indigo-500/20 shrink-0">
                <Icon name="Planet" weight="fill" className="text-xl" />
            </div>
            <div className="flex flex-col leading-tight hidden sm:flex">
                <span className="font-black text-sm tracking-tight text-white uppercase">Xray-редактор</span>
                {connected ? (
                    <span className="text-[10px] text-emerald-400 font-bold flex items-center gap-1">
                        <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />
                        Подключено к панели
                    </span>
                ) : (
                    <span className="text-[10px] text-slate-500 font-medium">Локальный режим</span>
                )}
            </div>

            {/* Diagnostics badge */}
            {(criticalCount > 0 || warningCount > 0) && (
                <div
                    onClick={onOpenDiagnostics}
                    className={`flex items-center gap-2 px-3 py-1 rounded-full border cursor-pointer transition-all hover:scale-105 active:scale-95 ml-2 ${
                        criticalCount > 0
                            ? 'text-rose-400 bg-rose-400/10 border-rose-400/20 animate-pulse shadow-[0_0_10px_rgba(244,63,94,0.2)]'
                            : 'text-amber-400 bg-amber-400/10 border-amber-400/20'
                    }`}
                >
                    <Icon name={criticalCount > 0 ? 'XCircle' : 'Warning'} weight="bold" />
                    <span className="text-[10px] font-black uppercase hidden md:inline">
                        {criticalCount > 0 ? `${criticalCount} критич. ошибок` : `${warningCount} предупреждений`}
                    </span>
                </div>
            )}
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-1.5 md:gap-3">
            {/* Cloud controls (connected) */}
            {connected && (
                <div className="flex items-center bg-slate-950/50 border border-slate-800 rounded-xl p-1 gap-1 h-11">
                    <button
                        onClick={onOpenSwitchProfile}
                        className="w-9 h-9 flex items-center justify-center hover:bg-slate-800 rounded-lg text-slate-400 hover:text-indigo-400 transition-all"
                        title="Сменить профиль"
                    >
                        <Icon name="ListDashes" weight="bold" />
                    </button>
                    <button
                        onClick={onPush}
                        className={`flex items-center justify-center gap-2 px-4 h-9 rounded-lg font-bold text-xs transition-all duration-300 ${
                            pushStage === 'confirm'
                                ? 'bg-amber-500 text-black shadow-[0_0_15px_rgba(245,158,11,0.4)] animate-bounce'
                                : 'bg-indigo-600/10 text-indigo-400 hover:bg-indigo-600 hover:text-white'
                        }`}
                    >
                        <Icon name={pushStage === 'confirm' ? 'SealCheck' : 'CloudArrowUp'} weight="bold" className="text-base" />
                        <span className="hidden lg:inline">{pushStage === 'confirm' ? 'Подтвердить?' : 'Сохранить'}</span>
                    </button>
                    <div className="w-px h-4 bg-slate-800 mx-1" />
                    <button
                        onClick={onDisconnect}
                        className="w-9 h-9 flex items-center justify-center hover:bg-rose-500/10 rounded-lg text-slate-600 hover:text-rose-500 transition-all"
                        title="Отключиться"
                    >
                        <Icon name="LinkBreak" weight="bold" />
                    </button>
                </div>
            )}

            {/* Connect Cloud (disconnected) */}
            {!connected && (
                <Button
                    variant="secondary"
                    onClick={onOpenRemnawave}
                    className="text-xs h-11 px-4 border-indigo-500/20 bg-indigo-500/5 hover:bg-indigo-500/10"
                >
                    <Icon name="Cloud" /> <span className="hidden md:inline">Загрузить профиль</span>
                </Button>
            )}

            <div className="w-px h-8 bg-slate-800/50 mx-1 hidden sm:block" />

            {/* File / Download */}
            <div className="flex gap-1.5 h-11 items-center bg-slate-950/50 p-1 rounded-xl border border-slate-800">
                <label
                    className="bg-slate-800 hover:bg-slate-700 text-slate-200 p-2 w-9 h-9 rounded-lg cursor-pointer transition-all border border-slate-700 flex items-center justify-center text-sm"
                    title="Загрузить JSON"
                >
                    <Icon name="FolderOpen" />
                    <input type="file" className="hidden" accept=".json" onChange={onFileUpload} />
                </label>
                <Button variant="success" onClick={onDownload} icon="DownloadSimple" className="rounded-lg h-9 px-4 text-sm shadow-none" disabled={!hasConfig}>
                    <span className="hidden md:inline text-xs">Скачать</span>
                </Button>
            </div>

            <div className="w-px h-8 bg-slate-800/50 mx-1 hidden sm:block" />

            <button
                onClick={onOpenAbout}
                className="h-11 px-3 flex items-center justify-center hover:bg-slate-800 rounded-lg text-slate-400 hover:text-white transition-all border border-slate-800 bg-slate-950/50"
                title="О редакторе"
            >
                <Icon name="Info" className="text-lg" />
            </button>

            <a
                href="https://xtls.github.io/"
                target="_blank"
                rel="noopener noreferrer"
                className="hidden sm:flex items-center gap-2 px-4 h-11 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 hover:bg-indigo-600 hover:text-white transition-all font-bold text-xs uppercase tracking-wider"
            >
                <Icon name="BookOpen" weight="bold" />
                Docs
            </a>
        </div>
    </nav>
);
