import { getSharedProtoWorker } from './proto-worker';

export const binaryCache = new Map<string, ArrayBuffer>();
const DB_NAME = 'GeoCacheDB';
const STORE_NAME = 'geo_data';

export const initDB = (): Promise<IDBDatabase> => {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, 1);
        request.onupgradeneeded = () => {
            if (!request.result.objectStoreNames.contains(STORE_NAME)) {
                request.result.createObjectStore(STORE_NAME);
            }
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
};

export const loadCachedData = async (key: string): Promise<any> => {
    try {
        const db = await initDB();
        return new Promise((resolve, reject) => {
            const tx = db.transaction(STORE_NAME, 'readonly');
            const store = tx.objectStore(STORE_NAME);
            const req = store.get(key);
            req.onsuccess = () => resolve(req.result || null);
            req.onerror = () => reject(req.error);
        });
    } catch { return null; }
};

export const saveCachedData = async (key: string, data: any, meta: any, rawBuffer?: ArrayBuffer) => {
    try {
        const db = await initDB();
        return new Promise((resolve, reject) => {
            const tx = db.transaction(STORE_NAME, 'readwrite');
            const store = tx.objectStore(STORE_NAME);
            const payload: any = { meta: { ...meta, timestamp: Date.now() }, data };
            if (rawBuffer) payload.buffer = rawBuffer;
            const req = store.put(payload, key);
            req.onsuccess = () => resolve(true);
            req.onerror = () => reject(req.error);
        });
    } catch (err) { console.warn("Geo cache write failed", err); }
};

// Кеш в памяти
let memCache: { geosite: any[], geoip: any[] } = { geosite: [], geoip: [] };
let fetchPromises: { geosite?: Promise<any[]>, geoip?: Promise<any[]> } = {};

export const getDefaultGeoList = (type: 'geosite' | 'geoip'): Promise<any[]> => {
    if (memCache[type] && memCache[type].length > 0) {
        return Promise.resolve(memCache[type]);
    }
    
    if (fetchPromises[type]) return fetchPromises[type]!;

    const promise = new Promise<any[]>(async (resolve) => {
        const geositeUrl = "https://cdn.jsdelivr.net/gh/v2fly/domain-list-community@release/dlc.dat";
        const geoipUrl = "https://cdn.jsdelivr.net/gh/v2fly/geoip@release/geoip.dat";
        const url = type === 'geosite' ? geositeUrl : geoipUrl;
        const CACHE_TTL = 24 * 60 * 60 * 1000;

        const cache = await loadCachedData(url);
        const now = Date.now();
        const needsUpdate = !cache || (now - (cache.meta?.timestamp || 0) > CACHE_TTL);

        if (!needsUpdate && cache?.data) {
            memCache[type] = cache.data || [];
            resolve(memCache[type]);
            return;
        }

        const worker = getSharedProtoWorker();
        
        const handleMessage = (e: MessageEvent) => {
            const { type: msgType, targetType, data, meta } = e.data;
            const t = targetType || msgType; 
            
            let d = data || e.data.data;
            if (msgType === 'cache_hit' && cache?.data) {
                d = cache.data;
            }
            
            if (msgType === 'success' || msgType === 'cache_hit' || msgType === type) {
                if (t === type) {
                    d = d ||[];
                    if (msgType === 'success') saveCachedData(url, d, meta);
                    memCache[type] = d;
                    resolve(d);
                    worker.removeEventListener('message', handleMessage);
                    fetchPromises[type] = undefined;
                }
            }
        };
        
        worker.addEventListener('message', handleMessage);
        worker.postMessage({ type, cachedMeta: cache?.meta });
    });

    fetchPromises[type] = promise;
    return promise;
};
