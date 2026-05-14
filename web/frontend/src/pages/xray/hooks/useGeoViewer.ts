// @ts-nocheck
import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { toast } from 'sonner';
import { getSharedProtoWorker } from '../utils/proto-worker';
import { binaryCache, loadCachedData, saveCachedData, getDefaultGeoList } from '../utils/geo-data';

export interface GeoItem { code: string; count: number; }

export const useGeoViewer = () => {
    const fileInputRef = useRef<HTMLInputElement>(null);
    const customWorkerRef = useRef<Worker | null>(null);

    const [activeTab, setActiveTab] = useState<'geosite' | 'geoip' | 'custom'>(() => (localStorage.getItem('geo_tab') as any) || 'geosite');
    const [customUrl, setCustomUrl] = useState(() => localStorage.getItem('geo_url') || "");
    const [customFormat, setCustomFormat] = useState<'text' | 'geosite' | 'geoip'>(() => (localStorage.getItem('geo_format') as any) || 'geoip');
    
    const [customFileBuffer, setCustomFileBuffer] = useState<ArrayBuffer | null>(null);
    const [customData, setCustomData] = useState<GeoItem[]>([]);
    
    const [geoSites, setGeoSites] = useState<GeoItem[]>([]);
    const [geoIps, setGeoIps] = useState<GeoItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [customLoading, setCustomLoading] = useState(false);
    
    const [search, setSearch] = useState("");
    const [debouncedSearch, setDebouncedSearch] = useState("");
    
    const [isDeepSearch, setIsDeepSearch] = useState(false);
    const [deepSearchLoading, setDeepSearchLoading] = useState(false);
    const [deepSearchResults, setDeepSearchResults] = useState<GeoItem[] | null>(null);

    const [viewTag, setViewTag] = useState<{ tag: string, code: string, url?: string, format?: string } | null>(null);

    // Persistence
    useEffect(() => {
        localStorage.setItem('geo_tab', activeTab);
        localStorage.setItem('geo_url', customUrl);
        localStorage.setItem('geo_format', customFormat);
    }, [activeTab, customUrl, customFormat]);

    // Search Debounce
    useEffect(() => {
        const timer = setTimeout(() => setDebouncedSearch(search), 300);
        return () => clearTimeout(timer);
    }, [search]);

    // Load initial data
    useEffect(() => {
        let isMounted = true;
        setLoading(true);

        const loadData = async () => {
            try {
                const [sites, ips] = await Promise.all([
                    getDefaultGeoList('geosite'),
                    getDefaultGeoList('geoip')
                ]);
                if (isMounted) {
                    setGeoSites(sites);
                    setGeoIps(ips);
                    setLoading(false);
                }
            } catch (e) {
                if (isMounted) setLoading(false);
            }
        };

        loadData();
        return () => { isMounted = false; };
    }, []);

    // Load custom cached data
    useEffect(() => {
        if (activeTab === 'custom' && customUrl && customUrl.startsWith('http')) {
            loadCachedData(customUrl).then(cache => {
                if (cache?.data) {
                    setCustomData(cache.data);
                } else if (!customFileBuffer) { 
                    setCustomData([]);
                }
            });
        }
    }, [customUrl, activeTab, customFileBuffer]);

    // Deep Search Logic
    useEffect(() => {
        if (!isDeepSearch || debouncedSearch.length < 2) {
            setDeepSearchResults(null);
            setDeepSearchLoading(false);
            return;
        }

        let isCancelled = false;
        setDeepSearchLoading(true);

        const currentUrl = activeTab === 'geosite' 
            ? "https://cdn.jsdelivr.net/gh/v2fly/domain-list-community@release/dlc.dat" 
            : activeTab === 'geoip' 
                ? "https://cdn.jsdelivr.net/gh/v2fly/geoip@release/geoip.dat" 
                : customUrl;
        
        const format = activeTab === 'custom' ? customFormat : activeTab;

        if (format === 'text') {
            setDeepSearchResults(customData.filter(d => d.code.toLowerCase().includes(debouncedSearch.toLowerCase())));
            setDeepSearchLoading(false);
            return;
        }

        const loadDeepSearch = async () => {
            let buffer = customFileBuffer || binaryCache.get(currentUrl);
            
            if (!buffer) {
                const cached = await loadCachedData(currentUrl + "_raw");
                if (cached && cached.buffer) {
                    buffer = cached.buffer;
                    binaryCache.set(currentUrl, buffer);
                }
            }

            if (isCancelled) return;

            const worker = getSharedProtoWorker();
            const handleMessage = (e: MessageEvent) => {
                if (isCancelled) return;
                if (e.data.type === 'deep_search_result') {
                    setDeepSearchResults(e.data.data);
                    setDeepSearchLoading(false);
                    worker.removeEventListener('message', handleMessage);
                } else if (e.data.error) {
                    toast.error("Deep search error", { description: e.data.error });
                    setDeepSearchLoading(false);
                    worker.removeEventListener('message', handleMessage);
                }
            };

            worker.addEventListener('message', handleMessage);

            worker.postMessage({
                type: 'deep_search',
                dataType: format,
                query: debouncedSearch,
                customUrl: currentUrl,
                fileBuffer: buffer
            });
        };

        loadDeepSearch();

        return () => { isCancelled = true; };
    }, [debouncedSearch, isDeepSearch, activeTab, customUrl, customFormat, customFileBuffer, customData]);

    const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setCustomLoading(true);
        setCustomUrl(file.name); 
        setCustomFileBuffer(null);

        try {
            if (customFormat === 'text') {
                const text = await file.text();
                const lines = text.split('\n').map(l => l.trim()).filter(l => l && !l.startsWith('#') && !l.startsWith('//'));
                const formattedData = lines.map(line => ({ code: line, count: 1 }));
                setCustomData(formattedData);
                setViewTag(null);
                toast.success(`Loaded ${formattedData.length} items from local file`);
                setCustomLoading(false);
            } else {
                const buffer = await file.arrayBuffer();
                setCustomFileBuffer(buffer);

                const worker = getSharedProtoWorker();
                const handleMessage = (evt: MessageEvent) => {
                    if (evt.data.error) toast.error("Failed to parse DAT", { description: evt.data.error });
                    else if (evt.data.type === 'success') {
                        setCustomData(evt.data.data);
                        setViewTag(null);
                        toast.success(`Loaded ${evt.data.data.length} categories from local file`);
                    }
                    setCustomLoading(false);
                    worker.removeEventListener('message', handleMessage);
                };

                worker.addEventListener('message', handleMessage);
                worker.postMessage({ type: 'custom', fileBuffer: buffer, dataType: customFormat });
            }
        } catch (err: any) {
            toast.error("File read error", { description: err.message });
            setCustomLoading(false);
        }
        e.target.value = '';
    };

    const fetchCustomList = async () => {
        if (!customUrl || customUrl.includes('.')) { 
            if (customFileBuffer) return toast.info("Local file already loaded");
        }
        if (!customUrl.startsWith('http')) return toast.error("Please enter a valid URL");
        
        setCustomLoading(true);
        setCustomFileBuffer(null);

        try {
            const myProxy = `https://crs.bropines.workers.dev/${customUrl}`;
            let targets = [];
            if (customUrl.includes('raw.githubusercontent.com')) {
                targets = [customUrl, myProxy, `https://mirror.ghproxy.com/${customUrl}`];
            } else if (customUrl.includes('github.com')) {
                targets = [myProxy, `https://mirror.ghproxy.com/${customUrl}`, `https://ghproxy.net/${customUrl}`, customUrl];
            } else {
                targets = [customUrl, myProxy];
            }
            
            let res;
            for (const target of targets) { 
                try { 
                    res = await fetch(target);
                    if (res.ok) break;
                } catch (e) {} 
            }
            if (!res || !res.ok) throw new Error("Failed to fetch list from URL");

            if (customFormat === 'text') {
                const text = await res.text();
                const lines = text.split('\n').map(l => l.trim()).filter(l => l && !l.startsWith('#') && !l.startsWith('//'));
                const formattedData = lines.map(line => ({ code: line, count: 1 }));
                
                await saveCachedData(customUrl, formattedData, { size: text.length });
                setCustomData(formattedData);
                setViewTag(null);
                toast.success(`Loaded ${formattedData.length} items`);
                setCustomLoading(false);
            } else {
                const buffer = await res.arrayBuffer();
                binaryCache.set(customUrl, buffer);
                await saveCachedData(customUrl + "_raw", null, { timestamp: Date.now() }, buffer);

                const worker = getSharedProtoWorker();
                const handleMessage = async (e: MessageEvent) => {
                    if (e.data.error) toast.error("Failed to parse DAT", { description: e.data.error });
                    else if (e.data.type === 'success') {
                        await saveCachedData(customUrl, e.data.data, e.data.meta || { timestamp: Date.now() });
                        setCustomData(e.data.data);
                        setViewTag(null);
                        toast.success(`Loaded ${e.data.data.length} categories`);
                    }
                    setCustomLoading(false);
                    worker.removeEventListener('message', handleMessage);
                };

                worker.addEventListener('message', handleMessage);
                worker.postMessage({ type: 'custom', fileBuffer: buffer, dataType: customFormat });
            }
        } catch (err: any) {
            toast.error("Failed to fetch list", { description: err.message });
            setCustomLoading(false);
        }
    };

    const displayData = useMemo(() => {
        if (isDeepSearch && deepSearchResults !== null) {
            return deepSearchResults;
        }

        let currentData: GeoItem[] = [];
        if (activeTab === 'geosite') currentData = geoSites;
        if (activeTab === 'geoip') currentData = geoIps;
        if (activeTab === 'custom') currentData = customData;

        if (!debouncedSearch || isDeepSearch) return currentData;
        const lowerSearch = debouncedSearch.toLowerCase();
        return currentData.filter(item => item.code.toLowerCase().includes(lowerSearch));
    }, [activeTab, geoSites, geoIps, customData, debouncedSearch, isDeepSearch, deepSearchResults]);

    const handleTabChange = useCallback((tab: 'geosite' | 'geoip' | 'custom') => {
        setActiveTab(tab);
        setSearch("");
        setDebouncedSearch("");
        setIsDeepSearch(false);
        setViewTag(null);
    }, []);

    return {
        activeTab,
        handleTabChange,
        customUrl,
        setCustomUrl,
        customFormat,
        setCustomFormat,
        customFileBuffer,
        loading,
        customLoading,
        search,
        setSearch,
        isDeepSearch,
        setIsDeepSearch,
        deepSearchLoading,
        displayData,
        viewTag,
        setViewTag,
        fileInputRef,
        handleFileUpload,
        fetchCustomList
    };
};
