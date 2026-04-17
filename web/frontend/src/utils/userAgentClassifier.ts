export type UserAgentClass = 'valid' | 'link_in_ua' | 'bot_library' | 'stub' | 'empty' | 'unknown'

const WHITELIST = [
  /^Happ\//i, /^Stash\//i, /^Streisand\//i, /^V2Box\//i, /^Karing\//i,
  /^ShadowRocket\//i, /^FoXray\//i, /^Loon\//i, /^Wings\s?X\//i,
  /^v2rayNG\//i, /^NekoBox\//i, /^Exclave\//i, /^Matsuri\//i, /^SagerNet\//i,
  /^Hiddify\//i, /^HiddifyNext\//i,
  /^FlClash(?:\s?X)?\//i, /^ClashX(?:\s?Pro)?\//i,
  /^Clash(?:\s?Verge)?(?:\s?Rev)?\//i, /^ClashMeta\//i,
  /^Mihomo(?:\s?Party)?\//i, /^koala[-\s]?clash\//i, /^Throne\//i,
  /^v2rayN\//i, /^Nekoray(?:NG)?\//i,
  /^sing-?box\//i, /^Xray\//i,
]

const LINK_IN_UA = [
  /^(?:vless|vmess|trojan|ss|hysteria2?|tuic|socks5?|shadowsocks|wireguard):\/\//i,
  /^https?:\/\//i,
]

const BOT_LIBRARY = [
  /^Go-http-client\//i, /^curl\//i, /^Wget\//i,
  /^python-(?:requests|urllib|httpx)\//i, /^Java\//i,
  /^node(?:-fetch|-superagent)?\//i, /^axios\//i, /^undici/i,
  /^got\s?\(/i, /^PostmanRuntime\//i, /^Insomnia\//i, /^HTTPie\//i,
]

const STUB = [
  /^Mozilla\/5\.0\s*$/i,
]

export function classifyUserAgent(ua?: string | null): UserAgentClass {
  if (!ua || !ua.trim()) return 'empty'
  const s = ua.trim()
  if (WHITELIST.some(r => r.test(s))) return 'valid'
  if (LINK_IN_UA.some(r => r.test(s))) return 'link_in_ua'
  if (BOT_LIBRARY.some(r => r.test(s))) return 'bot_library'
  if (STUB.some(r => r.test(s))) return 'stub'
  return 'unknown'
}

export function uaBadgeTone(cls: UserAgentClass): 'red' | 'yellow' | 'gray' | null {
  switch (cls) {
    case 'link_in_ua':
    case 'bot_library':
      return 'red'
    case 'stub':
    case 'empty':
      return 'yellow'
    case 'unknown':
      return 'gray'
    case 'valid':
    default:
      return null
  }
}
