/**
 * Thin adapter over the admin-panel axios client.
 *
 * Originally this class talked to a Remnawave Panel directly using a
 * user-supplied access token (the upstream xray-config-ui-editor is a
 * standalone webapp). Inside our admin panel we already have an
 * authenticated JWT session and a backend proxy that wraps Panel calls
 * with RBAC, audit logging, and access-policy scoping, so we route the
 * editor's requests through `/api/v2/config-profiles/*` instead.
 *
 * `setToken`/`baseUrl` are kept as no-ops so the rest of the upstream
 * code (configStore, useRemnawaveEditor) keeps compiling.
 */
import client from '@/api/client';
import type { RemnawaveProfile } from '../types/remnawave.types';

export class RemnawaveClient {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    constructor(_baseUrl?: string) {
        // The admin panel's axios client is preconfigured with the right base URL
        // and JWT, so the constructor argument is intentionally ignored.
    }

    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    setToken(_token: string | null) {
        // JWT auth is handled by the global axios interceptor — nothing to do here.
    }

    async login(_username: string, _password: string): Promise<string> {
        // The editor lives inside an already-authenticated admin session, so
        // a separate Panel login is unnecessary. We return a sentinel string
        // to keep the legacy "connect via login" UI path satisfied.
        return 'session';
    }

    async getConfigProfiles(): Promise<RemnawaveProfile[]> {
        const { data } = await client.get('/config-profiles');
        // Backend already unwraps Panel's `{response: {configProfiles: [...]}}`
        // into `{items, total}`.
        return Array.isArray(data?.items) ? data.items : [];
    }

    async getConfigProfile(uuid: string): Promise<unknown> {
        const { data } = await client.get(`/config-profiles/${uuid}`);
        // Backend returns Panel's `response` payload. Panel nests the editable
        // JSON under `configProfile.config` (newer schema) or `config` (older).
        return data?.config ?? data?.configProfile?.config ?? data?.response?.config ?? null;
    }

    async updateConfigProfile(uuid: string, config: unknown): Promise<void> {
        // Backend wraps Panel's PATCH /api/config-profiles. Body is just the
        // raw editor config — the uuid travels in the URL.
        await client.patch(`/config-profiles/${uuid}`, config);
    }
}
