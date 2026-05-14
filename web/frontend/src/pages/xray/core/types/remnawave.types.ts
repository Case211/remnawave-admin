export interface RemnawaveProfile {
    uuid: string;
    name?: string;
    description?: string;
    [key: string]: unknown;
}

export interface RemnawaveConnectionState {
    url: string;
    token: string | null;
    connected: boolean;
    activeProfileUuid: string | null;
}
