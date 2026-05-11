import nacl from 'tweetnacl';

// Хелпер: Uint8Array -> Base64 URL-Safe String
// Xray использует этот формат (без padding "=" в конце)
const toBase64Url = (arr: Uint8Array): string => {
    return btoa(String.fromCharCode(...arr))
        .replace(/\+/g, '-')
        .replace(/\//g, '_')
        .replace(/=+$/, '');
};

export const generateUUID = (): string => {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
        return crypto.randomUUID();
    }
    // Fallback for non-secure contexts (http) or older browsers
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        const v = c === 'x' ? r : (r & 0x3) | 0x8;
        return v.toString(16);
    });
};

export const generateX25519Keys = () => {
    // TweetNaCl box.keyPair генерирует ключи на кривой Curve25519 (X25519),
    // которая используется в REALITY.
    const keyPair = nacl.box.keyPair();

    return {
        privateKey: toBase64Url(keyPair.secretKey),
        publicKey: toBase64Url(keyPair.publicKey)
    };
};