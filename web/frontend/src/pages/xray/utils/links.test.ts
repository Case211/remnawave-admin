import { expect, test, describe } from "vitest";
import { parseXrayLink, parseWireguardConfig } from "./link-parser";
import { generateXrayLink } from "./link-generator";

describe("Link Parser & Generator", () => {
    
    describe("VLESS parsing & generation", () => {
        const vlessLink = "vless://00000000-0000-0000-0000-000000000000@89.46.38.91:443?security=reality&sni=google.com&fp=chrome&pbk=pubkey&sid=shortid&spx=%2F&type=grpc&serviceName=vless-grpc#MyServer";

        test("should parse VLESS link correctly", () => {
            const parsed = parseXrayLink(vlessLink);
            expect(parsed).not.toBeNull();
            expect(parsed.protocol).toBe("vless");
            expect(parsed.tag).toBe("MyServer");
            expect(parsed.settings.vnext[0].address).toBe("89.46.38.91");
            expect(parsed.settings.vnext[0].port).toBe(443);
            expect(parsed.settings.vnext[0].users[0].id).toBe("00000000-0000-0000-0000-000000000000");
            expect(parsed.streamSettings.security).toBe("reality");
            expect(parsed.streamSettings.network).toBe("grpc");
            expect(parsed.streamSettings.realitySettings.publicKey).toBe("pubkey");
        });

        test("should generate VLESS link from object", () => {
            const obj = parseXrayLink(vlessLink);
            const generated = generateXrayLink(obj);
            expect(generated).toContain("vless://");
            expect(generated).toContain("89.46.38.91:443");
            expect(generated).toContain("security=reality");
            expect(generated).toContain("type=grpc");
            expect(generated).toContain("MyServer");
        });

        test("should parse xhttp + reality correctly", () => {
            const link = "vless://645fe702bf804f968d6c6e1d078de119@38.180.38.126:8443?encryption=none&type=xhttp&security=reality&sni=ya.ru&fp=random&pbk=2focynRNhiclDiJQF7pWuJcZMdWsRzHun80Bnp8YLBY&sid=aabbccdd&path=/x&mode=auto#%F0%9F%87%B0%F0%9F%87%BFNEO-KZ";
            const parsed = parseXrayLink(link);
            expect(parsed.streamSettings.network).toBe("xhttp");
            expect(parsed.streamSettings.xhttpSettings.path).toBe("/x");
            expect(parsed.streamSettings.xhttpSettings.mode).toBe("auto");
            expect(parsed.streamSettings.realitySettings.spiderX).toBe("/x");
            expect(parsed.tag).toBe("🇰🇿NEO-KZ");
        });
    });

    describe("Shadowsocks parsing", () => {
        test("should parse modern SS link (base64 userinfo)", () => {
            // aes-256-gcm:pass
            const ssLink = "ss://YWVzLTI1Ni1nY206cGFzcw@89.46.38.91:443#SS-Server";
            const parsed = parseXrayLink(ssLink);
            expect(parsed.protocol).toBe("shadowsocks");
            expect(parsed.settings.servers[0].method).toBe("aes-256-gcm");
            expect(parsed.settings.servers[0].password).toBe("pass");
        });

        test("should parse legacy SS link (full base64)", () => {
            // aes-256-gcm:pass@89.46.38.91:443
            const ssLink = "ss://YWVzLTI1Ni1nY206cGFzc0A4OS40Ni4zOC45MTo0NDM#SS-Legacy";
            const parsed = parseXrayLink(ssLink);
            expect(parsed.protocol).toBe("shadowsocks");
            expect(parsed.tag).toBe("SS-Legacy");
            expect(parsed.settings.servers[0].address).toBe("89.46.38.91");
            expect(parsed.settings.servers[0].port).toBe(443);
            expect(parsed.settings.servers[0].method).toBe("aes-256-gcm");
            expect(parsed.settings.servers[0].password).toBe("pass");
        });
    });

    describe("WireGuard / AmneziaWG parser", () => {
        const wgConfig = `
[Interface]
PrivateKey = myprivatekey
Address = 10.0.0.2/32
DNS = 1.1.1.1
MTU = 1420
Jc = 4
Jmin = 40
Jmax = 70
S1 = 5
S2 = 10
H1 = 0x01020304

[Peer]
PublicKey = peerpubkey
AllowedIPs = 0.0.0.0/0
Endpoint = 89.46.38.91:51820
        `;

        test("should parse AmneziaWG (finalmask) correctly", () => {
            const parsed = parseWireguardConfig(wgConfig, 'direct');
            expect(parsed.protocol).toBe("wireguard");
            expect(parsed.settings.secretKey).toBe("myprivatekey");
            expect(parsed.streamSettings.network).toBe("raw");
            expect(parsed.streamSettings.finalmask).toBeDefined();
            expect(parsed.settings.reserved).toEqual([5, 10, 0]);
        });

        test("should parse AmneziaWG (chained) correctly", () => {
            const result = parseWireguardConfig(wgConfig, 'chained');
            expect(result.multiple).toBe(true);
            expect(result.outbounds).toHaveLength(2);
            expect(result.outbounds[0].streamSettings.sockopt.dialerProxy).toBeDefined();
            expect(result.outbounds[1].tag).toBe(result.outbounds[0].streamSettings.sockopt.dialerProxy);
        });
    });
});
