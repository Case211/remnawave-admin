import { useState, useCallback } from 'react';
import { useConfigStore } from '../store/configStore';

export const useDnsEditor = () => {
    const { config, updateSection } = useConfigStore();
    const dns = config?.dns || {};
    const fakedns = config?.fakedns || [];

    const [activeTab, setActiveTab] = useState<'general' | 'servers' | 'hosts' | 'fakedns'>('servers');
    const [editingServerIdx, setEditingServerIdx] = useState<number | null>(null);
    const [rawMode, setRawMode] = useState(false);
    const [mobileEditMode, setMobileEditMode] = useState(false);

    const handleUpdateDns = useCallback((newDns: any) => {
        updateSection('dns', newDns);
    }, [updateSection]);

    const handleAddServer = useCallback((initialVal: any) => {
        const newServers = [...(dns.servers || []), initialVal];
        handleUpdateDns({ ...dns, servers: newServers });
        if (typeof initialVal !== 'string') {
            setEditingServerIdx(newServers.length - 1);
            setMobileEditMode(true);
        }
    }, [dns, handleUpdateDns]);

    const handleSelectServer = useCallback((idx: number) => {
        setEditingServerIdx(idx);
        setMobileEditMode(true);
    }, []);

    const handleDeleteServer = useCallback((idx: number) => {
        const newServers = [...(dns.servers || [])];
        newServers.splice(idx, 1);
        handleUpdateDns({ ...dns, servers: newServers });
        if (editingServerIdx === idx) {
            setEditingServerIdx(null);
            setMobileEditMode(false);
        }
    }, [dns, handleUpdateDns, editingServerIdx]);

    const handleUpdateServer = useCallback((val: any) => {
        if (editingServerIdx === null) return;
        const newServers = [...(dns.servers || [])];
        newServers[editingServerIdx] = val;
        handleUpdateDns({ ...dns, servers: newServers });
    }, [dns, editingServerIdx, handleUpdateDns]);

    const handleCompositeUpdate = useCallback((newVal: any) => {
        if (!newVal) return;
        if (newVal.dns) updateSection('dns', newVal.dns);
        if (newVal.fakedns) updateSection('fakedns', newVal.fakedns);
    }, [updateSection]);

    const updateHosts = useCallback((h: any) => {
        handleUpdateDns({ ...dns, hosts: h });
    }, [dns, handleUpdateDns]);

    const updateFakedns = useCallback((val: any) => {
        updateSection('fakedns', val);
    }, [updateSection]);

    return {
        dns,
        fakedns,
        activeTab,
        setActiveTab,
        editingServerIdx,
        setEditingServerIdx,
        rawMode,
        setRawMode,
        mobileEditMode,
        setMobileEditMode,
        handleUpdateDns,
        handleAddServer,
        handleSelectServer,
        handleDeleteServer,
        handleUpdateServer,
        handleCompositeUpdate,
        updateHosts,
        updateFakedns
    };
};
