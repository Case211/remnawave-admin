/// <reference lib="webworker" />
import * as protobuf from 'protobufjs';

const GEOIP_PROTO = `
syntax = "proto3";
package router;
message CIDR { bytes ip = 1; uint32 prefix = 2; }
message GeoIP { string country_code = 1; repeated CIDR cidr = 2; }
message GeoIPList { repeated GeoIP entry = 1; }
`;

const GEOSITE_PROTO = `
syntax = "proto3";
package router;
message Domain { enum Type { Plain = 0; Regex = 1; RootDomain = 2; Full = 3; } Type type = 1; string value = 2; }
message GeoSite { string countryCode = 1; repeated Domain domain = 2; }
message GeoSiteList { repeated GeoSite entry = 1; }
`;

let cachedData: any = null;
let cachedBuffer: ArrayBuffer | null = null;
let cachedType: string | null = null;

const formatIp = (bytes: Uint8Array) => {
    if (!bytes) return '';
    if (bytes.length === 4) return Array.from(bytes).join('.');
    if (bytes.length === 16) {
        const hex = [];
        for (let i = 0; i < 16; i += 2) hex.push(((bytes[i] << 8) | bytes[i + 1]).toString(16));
        return hex.join(':').replace(/(^|:)0(:0)+/g, '::');
    }
    return '';
};

const getDecodedData = (buffer: ArrayBuffer, type: string) => {
    console.log("getDecodedData called for type:", type, "buffer size:", buffer.byteLength);
    if (cachedBuffer === buffer && cachedType === type && cachedData) {
        console.log("Returning cached data");
        return cachedData;
    }

    const isGeoSite = type === 'geosite';
    const root = new protobuf.Root();
    console.log("Parsing protobuf schema...");
    protobuf.parse(isGeoSite ? GEOSITE_PROTO : GEOIP_PROTO, root);
    const ListType = root.lookupType(isGeoSite ? "router.GeoSiteList" : "router.GeoIPList");
    
    console.log("Decoding message...");
    const message = ListType.decode(new Uint8Array(buffer));
    const object = ListType.toObject(message, { defaults: true }) as any;
    console.log("Decoding complete, entry count:", object.entry?.length);

    cachedData = object;
    cachedBuffer = buffer;
    cachedType = type;

    return object;
};

self.onmessage = async (e: MessageEvent) => {
    const msg = e.data;
    console.log("Worker received message:", msg);
    const { type, dataType, targetCode, customUrl, fileBuffer, query } = msg;
    const isGeoSite = type === 'geosite' || dataType === 'geosite';

    try {
        console.log("Worker processing type:", type);
        let buffer = fileBuffer;

        const getBuffer = async () => {
            const url = customUrl || (isGeoSite ? "https://cdn.jsdelivr.net/gh/v2fly/domain-list-community@release/dlc.dat" : "https://cdn.jsdelivr.net/gh/v2fly/geoip@release/geoip.dat");
            const targets = [url, `https://crs.bropines.workers.dev/${url}`, `https://mirror.ghproxy.com/${url}`];
            console.log("Fetching buffer from:", url);
            for (const t of targets) {
                try {
                    const res = await fetch(t);
                    if (res.ok) {
                        const b = await res.arrayBuffer();
                        console.log("Fetch success from:", t, "size:", b.byteLength);
                        return b;
                    }
                } catch (err) { console.warn("Fetch failed for:", t); }
            }
            throw new Error("Failed to download DAT file");
        };

        if (!buffer) {
            console.log("Buffer missing, downloading fresh...");
            buffer = await getBuffer();
        }

        if (type === 'deep_search') {
            const object = getDecodedData(buffer, isGeoSite ? 'geosite' : 'geoip');
            const q = query.toLowerCase();
            const results = [];

            for (const en of object.entry) {
                let match = false;
                if (isGeoSite) {
                    const domains = en.domain || [];
                    for (let i = 0; i < domains.length; i++) {
                        if (domains[i].value && domains[i].value.toLowerCase().includes(q)) {
                            match = true; break;
                        }
                    }
                } else {
                    const cidrs = en.cidr || [];
                    for (let i = 0; i < cidrs.length; i++) {
                        const ipStr = formatIp(cidrs[i].ip);
                        if (ipStr.includes(q)) { match = true; break; }
                    }
                }

                if (match) {
                    results.push({
                        code: en.countryCode || en.country_code,
                        count: (en.domain || en.cidr || []).length
                    });
                }
            }
            self.postMessage({ type: 'deep_search_result', data: results });
            return;
        }

        if (type === 'get_details') {
            const object = getDecodedData(buffer, isGeoSite ? 'geosite' : 'geoip');
            const targetList = object.entry.find((en: any) => (en.countryCode || en.country_code) === targetCode);
            
            if (!targetList) {
                self.postMessage({ type: 'details', data: '' });
                return;
            }

            let resultStr = "";
            if (isGeoSite) {
                resultStr = (targetList.domain || []).map((d: any) => {
                    let prefix = "";
                    if (d.type === 1) prefix = "regexp:";
                    else if (d.type === 2) prefix = "domain:";
                    else if (d.type === 3) prefix = "full:";
                    return prefix + d.value;
                }).join('\n');
            } else {
                resultStr = (targetList.cidr || []).map((c: any) => `${formatIp(c.ip)}/${c.prefix}`).join('\n');
            }

            self.postMessage({ type: 'details', data: resultStr });
            return;
        }

        if (buffer) {
            console.log("Decoding buffer for standard load...");
            const object = getDecodedData(buffer, isGeoSite ? 'geosite' : 'geoip');
            const result = object.entry.map((en: any) => ({
                code: en.countryCode || en.country_code,
                count: (en.domain || en.cidr || []).length
            }));

            self.postMessage({ type: 'success', targetType: type, data: result });
            console.log("Success message sent");
        }

    } catch (err: any) {
        console.error("Worker error:", err);
        self.postMessage({ type: 'error', targetType: type, error: err.message });
    }
};
