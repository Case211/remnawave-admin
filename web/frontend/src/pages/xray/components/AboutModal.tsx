import { useEffect, useState } from 'react';
import { Icon } from './ui/Icon';
import { Button } from './ui/Button';

interface Commit {
    sha: string;
    commit: {
        message: string;
        author: {
            date: string;
            name: string;
        };
    };
    html_url: string;
}

export const AboutModal = ({ onClose }: { onClose: () => void }) => {
    const [commits, setCommits] = useState<Commit[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const cached = sessionStorage.getItem('changelog-cache');
        if (cached) {
            setCommits(JSON.parse(cached));
            setLoading(false);
            return;
        }

        fetch('https://api.github.com/repos/bropines/xray-config-ui-editor/commits?per_page=10')
            .then(res => res.json())
            .then(data => {
                if (Array.isArray(data)) {
                    setCommits(data);
                    sessionStorage.setItem('changelog-cache', JSON.stringify(data));
                }
            })
            .catch(err => console.error("Failed to fetch changelog", err))
            .finally(() => setLoading(false));
    }, []);

    const formatDate = (dateStr: string) => {
        const date = new Date(dateStr);
        return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
    };

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-md p-4 animate-in fade-in" onClick={onClose}>
            <div className="bg-slate-900 border border-slate-700/50 rounded-3xl p-6 max-w-lg w-full shadow-2xl flex flex-col max-h-[90vh] overflow-hidden" onClick={e => e.stopPropagation()}>
                {/* Header */}
                <div className="flex items-center justify-between mb-6 shrink-0">
                    <div className="flex items-center gap-3">
                        <div className="bg-gradient-to-br from-indigo-500 to-purple-600 p-3 rounded-2xl text-white shadow-lg shadow-indigo-500/20">
                            <Icon name="Planet" weight="fill" className="text-2xl" />
                        </div>
                        <div>
                            <div className="font-black text-white text-xl tracking-tight uppercase leading-none">Xray GUI</div>
                            <div className="text-[10px] text-slate-500 font-bold uppercase tracking-widest mt-1">Version 2.0.0 (Experimental)</div>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-slate-800 rounded-xl text-slate-500 transition-colors">
                        <Icon name="X" weight="bold" />
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto custom-scroll space-y-6 pr-1">
                    <div className="grid grid-cols-2 gap-3 shrink-0">
                        <a href="https://github.com/bropines/xray-config-ui-editor" target="_blank" className="bg-slate-950 border border-slate-800 rounded-2xl p-3 flex flex-col items-center gap-1.5 hover:border-indigo-500/50 transition-all hover:bg-indigo-500/5 group">
                            <Icon name="GithubLogo" className="text-2xl text-slate-400 group-hover:text-white transition-colors" />
                            <span className="text-[10px] font-bold text-slate-500 group-hover:text-slate-200">Repository</span>
                        </a>
                        <a href="https://boosty.to/pinus" target="_blank" className="bg-slate-950 border border-slate-800 rounded-2xl p-3 flex flex-col items-center gap-1.5 hover:border-rose-500/50 transition-all hover:bg-rose-500/5 group">
                            <Icon name="Heart" weight="fill" className="text-2xl text-rose-500 group-hover:scale-110 transition-transform" />
                            <span className="text-[10px] font-bold text-slate-500 group-hover:text-rose-200">Support Dev</span>
                        </a>
                        <a href="https://xtls.github.io/" target="_blank" className="col-span-2 bg-slate-950 border border-slate-800 rounded-2xl p-3 flex items-center justify-center gap-2 hover:border-blue-500/50 transition-all hover:bg-blue-500/5 group">
                            <Icon name="BookOpen" className="text-lg text-slate-400 group-hover:text-white transition-colors" />
                            <span className="text-[10px] font-bold text-slate-500 group-hover:text-slate-200">Official Xray-core Documentation</span>
                        </a>
                        <a href="https://warp-generator.github.io/" target="_blank" className="col-span-2 bg-slate-950 border border-slate-800 rounded-2xl p-3 flex items-center justify-center gap-2 hover:border-amber-500/50 transition-all hover:bg-amber-500/5 group">
                            <Icon name="Lightning" className="text-lg text-amber-400 group-hover:scale-110 transition-transform" />
                            <span className="text-[10px] font-bold text-slate-500 group-hover:text-amber-200">WARP Engine by warp-generator.github.io</span>
                        </a>
                    </div>

                    {/* Changelog Section */}
                    <div className="space-y-3">
                        <div className="flex items-center gap-2 px-1">
                            <Icon name="GitCommit" className="text-indigo-400" />
                            <span className="text-xs font-black uppercase text-slate-400 tracking-wider">What's New (Changelog)</span>
                        </div>
                        
                        <div className="bg-slate-950/50 border border-slate-800/50 rounded-2xl overflow-hidden">
                            {loading ? (
                                <div className="p-10 flex flex-col items-center justify-center gap-3 opacity-50">
                                    <Icon name="CircleNotch" className="text-2xl animate-spin text-indigo-400" />
                                    <span className="text-[10px] font-bold uppercase">Loading commits...</span>
                                </div>
                            ) : (
                                <div className="divide-y divide-slate-800/50">
                                    {commits.map((c) => (
                                        <a key={c.sha} href={c.html_url} target="_blank" className="block p-3 hover:bg-white/[0.02] transition-colors group">
                                            <div className="flex justify-between gap-4 mb-1">
                                                <div className="text-[11px] font-bold text-slate-200 line-clamp-2 leading-relaxed group-hover:text-indigo-300 transition-colors">
                                                    {c.commit.message.split('\n')[0]}
                                                </div>
                                                <div className="text-[10px] font-mono text-slate-600 shrink-0 mt-0.5 uppercase tracking-tighter">
                                                    {formatDate(c.commit.author.date)}
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-2">
                                                <div className="text-[9px] font-mono text-slate-500 bg-slate-900 px-1.5 py-0.5 rounded border border-slate-800 group-hover:border-indigo-500/30 transition-colors">
                                                    {c.sha.substring(0, 7)}
                                                </div>
                                                <div className="text-[9px] text-slate-600 italic">
                                                    by {c.commit.author.name}
                                                </div>
                                            </div>
                                        </a>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* Footer */}
                <div className="pt-6 shrink-0">
                    <Button variant="secondary" className="w-full py-2.5 rounded-2xl text-xs font-bold" onClick={onClose}>
                        Close
                    </Button>
                </div>
            </div>
        </div>
    );
};
