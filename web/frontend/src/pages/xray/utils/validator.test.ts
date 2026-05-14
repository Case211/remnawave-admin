import { expect, test, describe } from "vitest";
import { 
    isValidAddress, 
    isValidIP, 
    isValidDomain, 
    isValidPort, 
    validateOutbound 
} from "./validator";

describe("Validator Basic Utils", () => {
    test("isValidIP", () => {
        expect(isValidIP("89.46.38.91")).toBe(true);
        expect(isValidIP("127.0.0.1")).toBe(true);
        expect(isValidIP("2001:0db8:85a3:0000:0000:8a2e:0370:7334")).toBe(true);
        expect(isValidIP("not-an-ip")).toBe(false);
        expect(isValidIP("---")).toBe(false);
    });

    test("isValidDomain", () => {
        expect(isValidDomain("google.com")).toBe(true);
        expect(isValidDomain("localhost")).toBe(true);
        expect(isValidDomain("my.server.local")).toBe(true);
        expect(isValidDomain("invalid_domain")).toBe(true); // underscores are allowed in our config
        expect(isValidDomain("---")).toBe(false);
    });

    test("isValidAddress", () => {
        // Should support both
        expect(isValidAddress("89.46.38.91")).toBe(true);
        expect(isValidAddress("example.com")).toBe(true);
        expect(isValidAddress("---")).toBe(false);
    });

    test("isValidPort", () => {
        expect(isValidPort(443)).toBe(true);
        expect(isValidPort("80")).toBe(true);
        expect(isValidPort(65535)).toBe(true);
        expect(isValidPort(0)).toBe(false);
        expect(isValidPort(70000)).toBe(false);
        expect(isValidPort("abc")).toBe(false);
    });
});

describe("Xray Outbound Validation", () => {
    test("validateOutbound with valid IP", () => {
        const outbound = {
            tag: "proxy",
            protocol: "vless",
            settings: {
                vnext: [{
                    address: "89.46.38.91",
                    port: 443,
                    users: [{ id: "uuid" }]
                }]
            }
        };
        const errors = validateOutbound(outbound);
        expect(errors).toHaveLength(0);
    });

    test("validateOutbound with valid Domain", () => {
        const outbound = {
            tag: "proxy",
            protocol: "vmess",
            settings: {
                vnext: [{
                    address: "my.server.com",
                    port: 80,
                    users: [{ id: "uuid" }]
                }]
            }
        };
        const errors = validateOutbound(outbound);
        expect(errors).toHaveLength(0);
    });

    test("validateOutbound with invalid address", () => {
        const outbound = {
            tag: "proxy",
            protocol: "trojan",
            settings: {
                servers: [{
                    address: "---",
                    port: 443
                }]
            }
        };
        const errors = validateOutbound(outbound);
        expect(errors.some(e => e.field === "address")).toBe(true);
    });

    test("validateOutbound with flat settings (hysteria/socks)", () => {
        const outbound = {
            tag: "h2-out",
            protocol: "hysteria",
            settings: {
                address: "89.46.38.91",
                port: 443,
                password: "pass"
            }
        };
        const errors = validateOutbound(outbound);
        expect(errors).toHaveLength(0);
    });
});
