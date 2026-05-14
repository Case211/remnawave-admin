import { useXrayEditor } from './useXrayEditor';
import { validateInbound } from '../utils/validator';
import { createDefaultInbound } from '../utils/protocol-factories';
import type { Inbound } from '../store/configStore';

export const useInboundEditor = (data: Inbound, onSave: (data: Inbound) => void) => {
    return useXrayEditor<Inbound>({
        data: data || createDefaultInbound(),
        onSave,
        validate: validateInbound,
        onProtocolChange: (proto) => createDefaultInbound(proto)
    });
};
