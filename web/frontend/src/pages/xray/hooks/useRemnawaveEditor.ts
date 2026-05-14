import { useState, useEffect, useCallback } from 'react';
import { useConfigStore } from '../store/configStore';
import { RemnawaveClient, type RemnawaveProfile } from '../utils/remnawave-client';
import { toast } from 'sonner';

export const useRemnawaveEditor = (onClose: () => void) => {
    const { 
        remnawave, 
        connectRemnawaveToken, 
        fetchRemnawaveProfiles, 
        loadRemnawaveProfile,
        disconnectRemnawave 
    } = useConfigStore();
    
    const [step, setStep] = useState<'login' | 'select'>('login');
    const [loading, setLoading] = useState(false);

    // Form State
    const [url, setUrl] = useState(remnawave.url || "");
    const [apiToken, setApiToken] = useState(remnawave.token || "");
    
    // Profiles
    const [profiles, setProfiles] = useState<RemnawaveProfile[]>([]);

    const handleRefreshProfiles = useCallback(async () => {
        setLoading(true);
        try {
            const list = await fetchRemnawaveProfiles();
            setProfiles(list);
        } catch (e: any) {
            setStep('login');
        } finally {
            setLoading(false);
        }
    }, [fetchRemnawaveProfiles]);

    useEffect(() => {
        if (remnawave.connected) {
            setStep('select');
            handleRefreshProfiles();
        }
    }, [remnawave.connected, handleRefreshProfiles]);

    const handleConnect = useCallback(async () => {
        if (!url || !apiToken) {
            toast.error("Please fill URL and API Token");
            return;
        }
        setLoading(true);
        try {
            const client = new RemnawaveClient(url);
            client.setToken(apiToken);
            
            const loadedProfiles = await client.getConfigProfiles();
            
            // Если профили загрузились — токен валидный
            connectRemnawaveToken(url, apiToken);
            setProfiles(loadedProfiles);
            setStep('select');
        } catch (e: any) {
            console.error(e);
            toast.error("Connection failed", { description: "Invalid token or panel URL" });
        } finally {
            setLoading(false);
        }
    }, [url, apiToken, connectRemnawaveToken]);

    const handleSelectProfile = useCallback(async (uuid: string) => {
        setLoading(true);
        await loadRemnawaveProfile(uuid);
        setLoading(false);
        onClose();
    }, [loadRemnawaveProfile, onClose]);

    return {
        remnawave,
        step,
        setStep,
        loading,
        url,
        setUrl,
        apiToken,
        setApiToken,
        profiles,
        handleRefreshProfiles,
        handleConnect,
        handleSelectProfile,
        disconnectRemnawave
    };
};
