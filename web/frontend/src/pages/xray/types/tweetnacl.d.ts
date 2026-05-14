declare module 'tweetnacl' {
    export const box: {
        keyPair: () => { publicKey: Uint8Array; secretKey: Uint8Array };
    };
}