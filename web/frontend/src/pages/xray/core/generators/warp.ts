// @ts-nocheck
import nacl from 'tweetnacl';

export interface WarpAccount {
    id: string;
    token: string;
    privateKey: string;
    publicKey: string;
    peerPublicKey: string;
    endpoint: string;
    ipv4: string;
    ipv6: string;
    reserved: number[];
}

/**
 * Default fallback workers/proxies from warp-generator.github.io
 * Prioritizing known working ones based on user feedback.
 */
const DEFAULT_WARP_ENDPOINTS = [
    'https://warp-vercel-murex.vercel.app/api/warp-data',
    'https://xcui.bropines.workers.dev/',
    'https://warp-vercel-chi.vercel.app/api/warp-data',
    'https://warp.sub-aggregator.workers.dev',
    'https://www.warp-generator.workers.dev',
];

/**
 * Registers a new WARP device and returns account credentials.
 * Supports both "Smart Workers" (that return full JSON) and "CORS Proxies".
 */
export async function generateWarpAccount(customWorkerUrl?: string): Promise<WarpAccount> {
    const endpoints = customWorkerUrl ? [customWorkerUrl] : DEFAULT_WARP_ENDPOINTS;
    let lastError: any;

    for (const url of endpoints) {
        try {
            // Smart method detection: Vercel/Bropines usually need GET, others might need POST
            const isVercel = url.includes('vercel.app');
            const isBropines = url.includes('bropines');
            const method = (isVercel || isBropines) ? 'GET' : 'POST';
            
            const response = await fetch(url, {
                method,
                signal: AbortSignal.timeout(15000)
            });

            if (response.status === 429) {
                throw new Error("Rate limited (429). Please try another profile or wait.");
            }

            if (!response.ok) {
                const errText = await response.text();
                throw new Error(`Worker returned ${response.status}: ${errText.substring(0, 30)}`);
            }

            const rawData = await response.json();
            
            // Handle different response formats:
            // 1. { success: true, privKey, ... }
            // 2. { privKey, ... }
            const data = rawData.success === true ? rawData : rawData;

            if (data.privKey && data.peer_pub) {
                return {
                    id: data.id || "",
                    token: data.token || "",
                    privateKey: data.privKey,
                    publicKey: "",
                    peerPublicKey: data.peer_pub,
                    endpoint: data.peer_endpoint || "engage.cloudflareclient.com:2408",
                    ipv4: data.client_ipv4,
                    ipv6: data.client_ipv6,
                    reserved: data.reserved || [0, 0, 0]
                };
            }
            
            throw new Error("Invalid worker response format");
            
        } catch (e: any) {
            console.warn(`Endpoint failed ${url}:`, e.message);
            lastError = e;
            
            // If it's a 429, don't immediately give up on the whole process, 
            // but the loop will move to the next endpoint.
        }
    }

    throw lastError || new Error("All registration endpoints are currently offline.");
}

/**
 * Full 3-step registration flow using a CORS proxy.
 */
async function performFullRegistrationFlow(proxyUrl: string): Promise<WarpAccount> {
    const keyPair = nacl.box.keyPair();
    const privateKey = btoa(String.fromCharCode(...keyPair.secretKey));
    const publicKey = btoa(String.fromCharCode(...keyPair.publicKey));

    // Step 1: Reg
    const regResponse = await cloudflareApi(proxyUrl, 'POST', 'reg', {
        install_id: "",
        tos: new Date().toISOString(),
        key: publicKey,
        fcm_token: "",
        type: "ios",
        locale: "en_US"
    });

    const id = regResponse.result.id;
    const token = regResponse.result.token;

    // Step 2: Enable WARP
    const warpResponse = await cloudflareApi(proxyUrl, 'PATCH', `reg/${id}`, { warp_enabled: true }, token);
    
    const config = warpResponse.result.config;
    const peer = config.peers[0];
    const reserved = config.interface.reserved || [0, 0, 0];

    return {
        id,
        token,
        privateKey,
        publicKey,
        peerPublicKey: peer.public_key,
        endpoint: peer.endpoint.host,
        ipv4: config.interface.addresses.v4,
        ipv6: config.interface.addresses.v6,
        reserved
    };
}
