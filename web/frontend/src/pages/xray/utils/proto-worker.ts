import GeoWorker from './geo.worker?worker';

// Shared singleton worker instance to preserve cached data in memory
let sharedWorker: Worker | null = null;

/**
 * Gets or creates the shared GeoWorker instance.
 * Using a singleton ensures that decoded protobuf data stays in worker memory
 * between different extraction requests, drastically improving performance.
 */
export const getSharedProtoWorker = () => {
    if (!sharedWorker) {
        sharedWorker = new GeoWorker();
    }
    return sharedWorker;
};

// For backward compatibility or cases where a fresh worker is explicitly needed
export const createProtoWorker = () => {
    return new GeoWorker();
};