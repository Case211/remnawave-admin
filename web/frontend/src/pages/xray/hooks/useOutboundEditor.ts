// @ts-nocheck
import { useXrayEditor } from './useXrayEditor';
import { validateOutbound, validateWireguard, checkOutboundDuplication } from '../utils/validator';
import type { ValidationError } from '../utils/validator';
import { createDefaultOutbound } from '../utils/protocol-factories';
import { useConfigStore } from '../store/configStore';
import type { Outbound } from '../store/configStore';
import { useCallback } from 'react';
import { toast } from 'sonner';

export const useOutboundEditor = (data: Outbound, onSave: (data: Outbound) => void, index: number | null) => {
    const { config } = useConfigStore();

    const validate = useCallback((local: Outbound) => {
        const baseErrors = validateOutbound(local);
        const wgErrors = local.protocol === 'wireguard' ? validateWireguard(local) : [];
        return [...baseErrors, ...wgErrors];
    }, []);

    const editor = useXrayEditor<Outbound>({
        data: data || createDefaultOutbound(),
        onSave: (local) => {
            // Проверка дубликатов перед окончательным сохранением
            const duplicateTag = checkOutboundDuplication(local, config?.outbounds || [], index);
            if (duplicateTag) {
                if (!confirm(`Duplicate detected! Similar configuration already exists in outbound tag: "${duplicateTag}". Save anyway?`)) {
                    return;
                }
            }
            onSave(local);
        },
        validate,
        onProtocolChange: (proto) => createDefaultOutbound(proto)
    });

    const wgPeerErrors = Object.fromEntries(
        editor.errors
            .filter(e => e.field.startsWith('peer_'))
            .map(e => [e.field, e.message])
    );

    return {
        ...editor,
        wgPeerErrors
    };
};
