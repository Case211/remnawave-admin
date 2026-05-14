// @ts-nocheck
import { create } from 'zustand';
import { produce } from 'immer';
import { persist, createJSONStorage } from 'zustand/middleware';
import { RemnawaveClient } from '../core/api/remnawave-client';
import { validateBalancer } from '../core/validators';
import { toast } from 'sonner';
import type { RemnawaveProfile } from '../core/types';

// Re-export types from core for backward compatibility
export type {
    XrayConfig,
    Inbound,
    Outbound,
    RoutingRule,
    Balancer,
    RoutingConfig,
    DnsConfig,
    DnsServerObject,
    LogConfig,
    ApiConfig,
    PolicyConfig,
    PolicyLevel,
    StatsConfig,
    ReverseConfig,
    FakednsPool,
    ObservatoryConfig,
    BurstObservatoryConfig,
} from '../core/types';

import type { XrayConfig, Inbound, Outbound, RoutingRule } from '../core/types';

// --- Интерфейсы Состояния Store ---

interface RemnawaveState {
    url: string;
    token: string | null;
    connected: boolean;
    activeProfileUuid: string | null;
}

interface ConfigState {
    config: XrayConfig | null;
    setConfig: (config: XrayConfig | null) => void;
    coreVersion: string;
    setCoreVersion: (version: string) => void;
    
    // UI & Generator Settings
    warpWorkerUrl: string;
    setWarpWorkerUrl: (url: string) => void;

    // Remnawave Actions

    remnawave: RemnawaveState;
    connectRemnawaveToken: (url: string, token: string) => void; 
    fetchRemnawaveProfiles: () => Promise<RemnawaveProfile[]>;
    loadRemnawaveProfile: (uuid: string) => Promise<void>;
    saveToRemnawave: () => Promise<void>;
    disconnectRemnawave: () => void;
    
    // Standard CRUD Actions
    updateSection: (section: keyof XrayConfig, data: any) => void;
    toggleSection: (section: keyof XrayConfig, defaultValue: any) => void;
    addItem: (section: 'inbounds' | 'outbounds', item: any) => void;
    updateItem: (section: 'inbounds' | 'outbounds', index: number, item: any) => void;
    deleteItem: (section: 'inbounds' | 'outbounds', index: number) => void;
    moveItem: (section: 'inbounds' | 'outbounds', fromIndex: number, toIndex: number) => void;
    addOutbounds: (items: any[]) => void;
    
    reorderRules: (newRules: RoutingRule[]) => void;
    initDns: () => void;
}

// --- Implementation ---

export const useConfigStore = create(
    persist<ConfigState>(
        (set, get) => ({
            config: null,
            coreVersion: 'v1.8.10',
            setCoreVersion: (version: string) => set({ coreVersion: version }),
            
            warpWorkerUrl: '',
            setWarpWorkerUrl: (url: string) => set({ warpWorkerUrl: url }),

            // --- Remnawave Connection ---
            remnawave: {
                url: '',
                token: null,
                connected: false,
                activeProfileUuid: null
            },

            disconnectRemnawave: () => set(produce((state) => {
                state.remnawave.token = null;
                state.remnawave.connected = false;
                state.remnawave.activeProfileUuid = null;
                toast.info("Соединение с панелью закрыто");
            })),

            connectRemnawaveToken: (url, token) => {
                if (!url || !token) {
                    toast.error("Нужны URL и токен");
                    return;
                }
                set(produce((state) => {
                    state.remnawave.url = url;
                    state.remnawave.token = token;
                    state.remnawave.connected = true;
                }));
                toast.success("Подключено к Remnawave");
            },

            /**
             * Auto-connect using the admin-panel session — there's no user-supplied
             * URL/token here. The RemnawaveClient adapter routes everything through
             * our `@/api/client` (JWT cookie + RBAC), so we just flip `connected`
             * and stash a sentinel so the url/token guards in the legacy actions
             * stay happy. Idempotent: bails out if already connected.
             */
            autoConnectAdminSession: () => {
                if (get().remnawave.connected) return;
                set(produce((state) => {
                    state.remnawave.url = 'admin-session';
                    state.remnawave.token = 'admin-session';
                    state.remnawave.connected = true;
                }));
            },

            fetchRemnawaveProfiles: async () => {
                // Admin-session auto-connect populates url/token with sentinels,
                // so the legacy guard becomes a no-op. Real auth happens at the
                // axios client layer.
                const client = new RemnawaveClient();
                try {
                    return await client.getConfigProfiles();
                } catch (e: any) {
                    if (e.message?.includes?.("401")) {
                        get().disconnectRemnawave();
                        toast.error("Сессия истекла");
                    }
                    throw e;
                }
            },

            loadRemnawaveProfile: async (uuid) => {
                const client = new RemnawaveClient();
                try {
                    const configData = await client.getConfigProfile(uuid);
                    set({ config: configData as XrayConfig });
                    set(produce((state) => {
                        state.remnawave.activeProfileUuid = uuid;
                    }));
                    toast.success("Профиль загружен");
                } catch (e: any) {
                    toast.error("Не удалось загрузить профиль");
                }
            },

            saveToRemnawave: async () => {
                const { activeProfileUuid } = get().remnawave;
                const { config } = get();

                if (!activeProfileUuid || !config) {
                    toast.error("Профиль не выбран");
                    return;
                }

                // --- КРИТИЧЕСКАЯ ВАЛИДАЦИЯ БАЛАНСИРОВЩИКОВ ПЕРЕД ПУШЕМ ---
                // filter(Boolean) защищает от null элементов в массиве (бывает после удаления)
                const balancers = (config.routing?.balancers || []).filter(Boolean);
                const invalidBalancer = balancers.find(b => validateBalancer(b).length > 0);
                
                if (invalidBalancer) {
                    toast.error("Push Blocked!", {
                        description: `Balancer "${invalidBalancer.tag}" has no target outbounds. Node will crash if you push this.`,
                        duration: 6000
                    });
                    return;
                }

                const client = new RemnawaveClient();
                try {
                    await client.updateConfigProfile(activeProfileUuid, config);
                    toast.success("Профиль сохранён в панели");
                } catch (e: any) {
                    toast.error("Не удалось отправить конфиг в панель");
                }
            },

            // --- Standard CRUD Actions ---
            
            setConfig: (config) => set({ config }),

            updateSection: (section, data) => set(produce((state) => {
                if (!state.config) {
                    state.config = { inbounds: [], outbounds: [] };
                }
                if (data !== undefined) {
                    state.config[section] = data;
                }
            })),

            toggleSection: (section, defaultValue) => set(produce((state) => {
                if (!state.config) return;
                if (state.config[section]) {
                    delete state.config[section];
                } else {
                    state.config[section] = defaultValue;
                }
            })),

            addItem: (section, item) => set(produce((state) => {
                if (state.config) {
                    state.config[section] = state.config[section] || [];
                    state.config[section].push(item);
                }
            })),

            addOutbounds: (items) => set(produce((state) => {
                if (!state.config) state.config = { inbounds: [], outbounds: [] };
                const existingTags = new Set(
                    (state.config.outbounds || []).filter(Boolean).map((o: any) => o.tag).filter(Boolean),
                );
                
                const cleanItems = items.map((item) => {
                    let tag = item.tag || `${item.protocol}-${Math.floor(Math.random() * 1000)}`;
                    
                    if (existingTags.has(tag)) {
                        const suffix = Math.random().toString(36).substring(2, 5);
                        tag = `${tag}-${suffix}`;
                    }
                    
                    existingTags.add(tag); // Добавляем в сет, чтобы избежать дублей внутри самой пачки импорта
                    return { ...item, tag };
                });
                
                state.config.outbounds.push(...cleanItems);
            })),

            updateItem: (section, index, item) => set(produce((state) => {
                if (state.config && state.config[section]) {
                    state.config[section][index] = item;
                }
            })),

            deleteItem: (section, index) => set(produce((state) => {
                if (state.config && state.config[section]) {
                    state.config[section].splice(index, 1);
                }
            })),
            
            moveItem: (section, fromIndex, toIndex) => set(produce((state) => {
                if (!state.config || !state.config[section]) return;
                const list = state.config[section];
                if (toIndex < 0 || toIndex >= list.length) return;
                
                const [movedItem] = list.splice(fromIndex, 1);
                list.splice(toIndex, 0, movedItem);
            })),

            reorderRules: (newRules) => set(produce((state) => {
                if (state.config) {
                    if (!state.config.routing) state.config.routing = { rules: [], balancers: [] };
                    state.config.routing.rules = newRules;
                }
            })),

            initDns: () => set(produce((state) => {
                if (state.config && !state.config.dns) {
                    state.config.dns = {
                        servers: ["1.1.1.1", "8.8.8.8", "localhost"],
                        queryStrategy: "UseIP",
                        tag: "dns_inbound"
                    };
                }
            }))
        }),
        {
            name: 'xray-config-storage',
            storage: createJSONStorage(() => localStorage),
            partialize: (state) => ({ 
                config: state.config,
                coreVersion: state.coreVersion,
                warpWorkerUrl: state.warpWorkerUrl,
                remnawave: { 
                    url: state.remnawave.url, 
                    token: state.remnawave.token, 
                    connected: state.remnawave.connected,
                    activeProfileUuid: state.remnawave.activeProfileUuid 
                } 
            }),
        }
    )
);