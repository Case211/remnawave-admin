import { useState, useEffect, useCallback, useMemo } from 'react';
import { useConfigStore, type XrayConfig } from '../store/configStore';
import { runFullDiagnostics } from '../utils/diagnostics';
import { parseJsonSubscription } from '../utils/link-parser';
import { toast } from 'sonner';

export const useAppLogic = () => {
    const {
        config,
        setConfig,
        deleteItem,
        moveItem,
        updateItem,
        addItem,
        addOutbounds,
        updateSection,
        remnawave,
        saveToRemnawave,
        disconnectRemnawave,
        initDns
    } = useConfigStore();

    // Modal states
    const [modal, setModal] = useState<{ type: string | null, data: any, index: number | null }>({ type: null, data: null, index: null });
    const [sectionModal, setSectionModal] = useState<{ open: boolean, title: string, section: string, data: any, schemaMode: any }>({
        open: false, title: "", section: "", data: null, schemaMode: "full"
    });
    const [remnawaveModalOpen, setRemnawaveModalOpen] = useState(false);
    const [batchModalOpen, setBatchModalOpen] = useState(false);
    const [geoViewerOpen, setGeoViewerOpen] = useState(false);
    const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
    const [aboutOpen, setAboutOpen] = useState(false);
    const [warpModalOpen, setWarpModalOpen] = useState(false);
    const [configInspectorOpen, setConfigInspectorOpen] = useState(false);
    
    // UI states
    const [rawMode, setRawMode] = useState(false);
    const [isDragging, setIsDragging] = useState(false);
    const [obSearch, setObSearch] = useState("");
    const [pushStage, setPushStage] = useState<'idle' | 'confirm'>('idle');

    useEffect(() => {
        if (pushStage === 'confirm') {
            const timer = setTimeout(() => setPushStage('idle'), 3000);
            return () => clearTimeout(timer);
        }
    }, [pushStage]);

    const handleRealPush = useCallback(() => {
        saveToRemnawave();
        setPushStage('idle');
    }, [saveToRemnawave]);

    const loadFile = useCallback((file: File) => {
        const reader = new FileReader();
        reader.onload = (e: ProgressEvent<FileReader>) => {
            try {
                const result = e.target?.result;
                if (typeof result === 'string') {
                    const parsed = JSON.parse(result);
                    
                    if (Array.isArray(parsed)) {
                        // Это JSON-подписка (массив конфигов)
                        const obs = parseJsonSubscription(result);
                        if (obs.length > 0) {
                            addOutbounds(obs);
                            toast.success(`Imported ${obs.length} nodes from JSON file`);
                        } else {
                            toast.error("JSON array detected, but no valid outbounds found");
                        }
                    } else {
                        // Это обычный конфиг (объект)
                        setConfig(parsed as XrayConfig);
                        toast.success("Configuration loaded from file");
                    }
                    setRawMode(false);
                }
            } catch { toast.error("Invalid JSON file"); }
        };
        reader.readAsText(file);
    }, [setConfig, addOutbounds]);

    const handleFileUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files?.[0]) loadFile(e.target.files[0]);
    }, [loadFile]);

    const downloadConfig = useCallback(() => {
        const a = document.createElement('a');
        a.href = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(config, null, 2));
        a.download = "config.json";
        a.click();
    }, [config]);

    const handleDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(true);
    }, []);

    const handleDragLeave = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        if (e.relatedTarget === null || !e.currentTarget.contains(e.relatedTarget as Node)) setIsDragging(false);
    }, []);

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
        if (e.dataTransfer.files[0]) loadFile(e.dataTransfer.files[0]);
    }, [loadFile]);

    const handleSaveModal = useCallback((data: any) => {
        const { type, index } = modal;
        if (type === 'inbound') index !== null ? updateItem('inbounds', index, data) : addItem('inbounds', data);
        if (type === 'outbound') index !== null ? updateItem('outbounds', index, data) : addItem('outbounds', data);
        setModal({ type: null, data: null, index: null });
    }, [modal, updateItem, addItem]);

    const handleSaveSection = useCallback((newData: any) => {
        updateSection(sectionModal.section as any, newData);
        setSectionModal(prev => ({ ...prev, open: false }));
    }, [sectionModal.section, updateSection]);

    const openSectionJson = useCallback((section: string, title: string, explicitData?: any) => {
        const modeMap: Record<string, string> = { inbounds: 'inbounds', outbounds: 'outbounds', routing: 'routing', dns: 'dns' };
        setSectionModal({
            open: true, title: title + " (JSON)", section,
            data: explicitData !== undefined ? explicitData : (config ? config[section as keyof typeof config] : (section === 'inbounds' || section === 'outbounds' ? [] : {})),
            schemaMode: modeMap[section] || 'full'
        });
    }, [config]);

    const diagnostics = useMemo(() => runFullDiagnostics(config), [config]);
    const criticalCount = useMemo(() => diagnostics.filter(d => d.severity === 'critical').length, [diagnostics]);
    const warningCount = useMemo(() => diagnostics.filter(d => d.severity === 'warning').length, [diagnostics]);

    const filteredOutbounds = useMemo(() => {
        return (config?.outbounds || [])
            .map((ob: any, i: number) => ({ ...ob, i }))
            .filter((ob: any) => {
                const q = obSearch.toLowerCase();
                if (!q) return true;
                const s = ob.settings || {};
                const vnext = s.vnext?.[0] || {};
                const server = s.servers?.[0] || s;
                return (
                    String(ob.tag || "").toLowerCase().includes(q) ||
                    String(ob.protocol || "").toLowerCase().includes(q) ||
                    String(vnext.address || server.address || "").toLowerCase().includes(q) ||
                    String(vnext.users?.[0]?.id || server.password || server.id || "").toLowerCase().includes(q)
                );
            });
    }, [config?.outbounds, obSearch]);

    return {
        config, setConfig, deleteItem, addItem, remnawave, disconnectRemnawave, initDns,
        modal, setModal,
        sectionModal, setSectionModal,
        remnawaveModalOpen, setRemnawaveModalOpen,
        batchModalOpen, setBatchModalOpen,
        geoViewerOpen, setGeoViewerOpen,
        diagnosticsOpen, setDiagnosticsOpen,
        aboutOpen, setAboutOpen,
        warpModalOpen, setWarpModalOpen,
        configInspectorOpen, setConfigInspectorOpen,
        rawMode, setRawMode,
        isDragging,
        obSearch, setObSearch,
        pushStage, setPushStage,
        handleRealPush,
        handleFileUpload,
        downloadConfig,
        handleDragOver,
        handleDragLeave,
        handleDrop,
        handleSaveModal,
        handleSaveSection,
        openSectionJson,
        diagnostics,
        criticalCount,
        warningCount,
        filteredOutbounds,
        moveItem
    };
};
