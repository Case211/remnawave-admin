import nacl from 'tweetnacl';

/**
 * Generates a v4 UUID using native crypto when available.
 */
export const generateUUID = (): string => {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
        return crypto.randomUUID();
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        const v = c === 'x' ? r : (r & 0x3) | 0x8;
        return v.toString(16);
    });
};

/**
 * Generates a random hex string of given length.
 * Used for XHTTP shortId and similar fields.
 */
export const generateShortId = (length = 8): string => {
    const chars = '0123456789abcdef';
    let result = '';
    for (let i = 0; i < length; i++) {
        result += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return result;
};

/**
 * Generates a Reality X25519 key pair (url-safe base64, no padding).
 */
export const generateRealityKeyPair = (): { privateKey: string; publicKey: string } => {
    const keypair = nacl.box.keyPair();
    const encode = (bytes: Uint8Array) =>
        btoa(String.fromCharCode(...bytes))
            .replace(/\+/g, '-')
            .replace(/\//g, '_')
            .replace(/=+$/, '');
    return {
        privateKey: encode(keypair.secretKey),
        publicKey: encode(keypair.publicKey),
    };
};

/**
 * Generates a random Reality spiderX path.
 * Usually a / followed by 4-8 random chars.
 */
export const generateRealitySpiderX = (): string => {
    const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
    let result = '/';
    const len = 4 + Math.floor(Math.random() * 5);
    for (let i = 0; i < len; i++) {
        result += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return result;
};

/**
 * Generates a list of Reality shortIds.
 */
export const generateRealityShortIds = (count = 1): string[] => {
    return Array.from({ length: count }, () => generateShortId(Math.random() > 0.5 ? 8 : 16));
};
