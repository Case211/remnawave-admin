import { useState, useCallback, useMemo } from 'react';
import { useConfigStore } from '../store/configStore';

export const useSettingsEditor = () => {
    const { config, updateSection, toggleSection, coreVersion, setCoreVersion } = useConfigStore();
    const [activeTab, setActiveTab] = useState<'general' | 'policy' | 'observatory'>('general');
    const [rawMode, setRawMode] = useState(false);

    const outboundTags = useMemo(() => (config?.outbounds || []).map(o => o.tag).filter(t => t), [config?.outbounds]);

    const coreSettings = useMemo(() => ({
        log: config?.log,
        api: config?.api,
        policy: config?.policy,
        observatory: config?.observatory,
        burstObservatory: config?.burstObservatory,
        stats: config?.stats
    }), [config]);

    const handleRawUpdate = useCallback((newVal: any) => {
        if (!newVal) return;
        if (newVal.log !== undefined) updateSection('log', newVal.log);
        if (newVal.api !== undefined) updateSection('api', newVal.api);
        if (newVal.policy !== undefined) updateSection('policy', newVal.policy);
        if (newVal.observatory !== undefined) updateSection('observatory', newVal.observatory);
        if (newVal.burstObservatory !== undefined) updateSection('burstObservatory', newVal.burstObservatory);
        if (newVal.stats !== undefined) updateSection('stats', newVal.stats);
    }, [updateSection]);

    const downloadCoreJson = useCallback(() => {
        const blob = new Blob([JSON.stringify(coreSettings, null, 2)], { type: "application/json" });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = "core-settings.json";
        a.click();
    }, [coreSettings]);

    return {
        config,
        coreVersion,
        setCoreVersion,
        activeTab,
        setActiveTab,
        rawMode,
        setRawMode,
        outboundTags,
        coreSettings,
        handleRawUpdate,
        downloadCoreJson,
        updateSection,
        toggleSection
    };
};
