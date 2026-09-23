// SPDX-License-Identifier: (GPL-2.0-only OR MIT)
/*
 * Шейпер клиентов ноды: свой потолок скорости на каждый адрес клиента.
 *
 * Скачивание (выход интерфейса) режется по EDT: программа назначает пакету
 * время отправки, а fq в корне его выдерживает. Пакет не клонируется и не
 * уходит в другое устройство, поэтому TCP на ноде видит обычное обратное
 * давление, а не потери.
 *
 * Отдача (вход интерфейса) режется полисером: сверх нормы пакеты
 * отбрасываются, и TCP на стороне клиента притормаживает сам — входящий
 * пакет придержать негде.
 *
 * В счёт идёт только трафик клиентов — пакеты на портах inbound'ов ноды
 * (карта rws_ports): на выходе по порту источника, на входе по порту
 * назначения. Собственные соединения ноды в интернет сюда не попадают,
 * иначе потолок достался бы адресам сайтов, а не клиентам.
 *
 * Режим штрафа: если клиент за окно прокачал больше порога (обе стороны
 * вместе), на заданное время его скорость падает до штрафной.
 *
 * Персональный лимит (мягкая блокировка юзера) живёт в карте rws_personal
 * по адресу клиента и от портов не зависит: урезанный клиент режется на
 * любой ноде, даже там, где общий шейпер выключен. Действует меньший из
 * потолков — общего, персонального и штрафного; 0 значит «без лимита».
 *
 * Пропущенный пакет получает вердикт TC_ACT_UNSPEC, а не TC_ACT_OK: так
 * проверка идёт дальше, и фильтры других сервисов на этом же хуке работают.
 */
#include <linux/bpf.h>
#include <linux/pkt_cls.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/ipv6.h>
#include <linux/in.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>

#define NSEC_PER_SEC 1000000000ULL

/* Без барьера clang сворачивает «нет персонального и порт не наш» в ИЛИ двух
 * указателей, а верификатор такое запрещает: pointer |= pointer prohibited. */
#ifndef barrier_var
#define barrier_var(var) asm volatile("" : "+r"(var))
#endif

/* Раскладку полей повторяет src/shaper.py (struct.pack) — менять вместе. */
struct shaper_cfg {
	__u64 l2_len;          /* 14 — Ethernet, 0 — L3-интерфейс без заголовка */
	__u64 down_rate;       /* байт/с на клиента, 0 — без потолка */
	__u64 up_rate;         /* байт/с на клиента, 0 — без потолка */
	__u64 horizon_ns;      /* дальше этого срока пакет не откладываем, а отбрасываем */
	__u64 burst_ns;        /* запас полисера на входе */
	__u64 pen_bytes;       /* порог окна; 0 — штраф выключен */
	__u64 pen_window_ns;
	__u64 pen_rate;        /* байт/с под штрафом */
	__u64 pen_duration_ns;
};

/* Адрес клиента: IPv6 как есть, IPv4 в виде ::ffff:a.b.c.d. */
struct client_key {
	__u32 addr[4];
};

struct client_state {
	__u64 down_last;       /* время ухода последнего пакета к клиенту */
	__u64 up_next;         /* виртуальные часы полисера отдачи */
	__u64 win_start;
	__u64 win_bytes;
	__u64 pen_until;
};

struct shaper_stats {
	__u64 delayed;         /* пакетов скачивания, придержанных до срока */
	__u64 dropped_down;
	__u64 dropped_up;
	__u64 penalties;
};

struct {
	__uint(type, BPF_MAP_TYPE_ARRAY);
	__uint(max_entries, 1);
	__type(key, __u32);
	__type(value, struct shaper_cfg);
} rws_cfg SEC(".maps");

struct {
	__uint(type, BPF_MAP_TYPE_HASH);
	__uint(max_entries, 64);
	__type(key, __u16);
	__type(value, __u8);
} rws_ports SEC(".maps");

/* Персональный лимит: байт/с в каждую сторону, 0 — без лимита. Раскладку
 * повторяет src/shaper.py (struct.pack) — менять вместе. */
struct personal_limit {
	__u64 down_rate;
	__u64 up_rate;
};

struct {
	__uint(type, BPF_MAP_TYPE_HASH);
	__uint(max_entries, 16384);
	__type(key, struct client_key);
	__type(value, struct personal_limit);
} rws_personal SEC(".maps");

/* LRU: клиенты уходят и приходят, место освобождается само. */
struct {
	__uint(type, BPF_MAP_TYPE_LRU_HASH);
	__uint(max_entries, 65536);
	__type(key, struct client_key);
	__type(value, struct client_state);
} rws_clients SEC(".maps");

struct {
	__uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
	__uint(max_entries, 1);
	__type(key, __u32);
	__type(value, struct shaper_stats);
} rws_stats SEC(".maps");

enum { ST_DELAYED, ST_DROPPED_DOWN, ST_DROPPED_UP, ST_PENALTIES };

static __always_inline void stat_inc(int which)
{
	__u32 zero = 0;
	struct shaper_stats *s = bpf_map_lookup_elem(&rws_stats, &zero);

	if (!s)
		return;
	if (which == ST_DELAYED)
		s->delayed++;
	else if (which == ST_DROPPED_DOWN)
		s->dropped_down++;
	else if (which == ST_DROPPED_UP)
		s->dropped_up++;
	else
		s->penalties++;
}

/* Адрес клиента и порт ноды из пакета. egress: клиент — получатель. */
static __always_inline int parse(struct __sk_buff *skb, __u32 l2, int egress,
				 struct client_key *key, __u16 *port)
{
	__u16 ports[2];

	if (skb->protocol == bpf_htons(ETH_P_IP)) {
		struct iphdr ip;
		__u32 ihl;

		if (bpf_skb_load_bytes(skb, l2, &ip, sizeof(ip)))
			return 0;
		if (ip.protocol != IPPROTO_TCP && ip.protocol != IPPROTO_UDP)
			return 0;
		/* У фрагментов, кроме первого, заголовка с портами нет */
		if (ip.frag_off & bpf_htons(0x1fff))
			return 0;
		ihl = ip.ihl * 4;
		if (ihl < sizeof(ip))
			return 0;
		if (bpf_skb_load_bytes(skb, l2 + ihl, ports, sizeof(ports)))
			return 0;
		key->addr[2] = bpf_htonl(0xffff);
		key->addr[3] = egress ? ip.daddr : ip.saddr;
	} else if (skb->protocol == bpf_htons(ETH_P_IPV6)) {
		struct ipv6hdr ip6;

		if (bpf_skb_load_bytes(skb, l2, &ip6, sizeof(ip6)))
			return 0;
		/* Цепочки расширенных заголовков не разбираем: клиентский TCP/UDP идёт без них */
		if (ip6.nexthdr != IPPROTO_TCP && ip6.nexthdr != IPPROTO_UDP)
			return 0;
		if (bpf_skb_load_bytes(skb, l2 + sizeof(ip6), ports, sizeof(ports)))
			return 0;
		if (egress)
			__builtin_memcpy(key->addr, ip6.daddr.in6_u.u6_addr32, sizeof(key->addr));
		else
			__builtin_memcpy(key->addr, ip6.saddr.in6_u.u6_addr32, sizeof(key->addr));
	} else {
		return 0;
	}

	*port = bpf_ntohs(egress ? ports[0] : ports[1]);
	return 1;
}

static __always_inline struct client_state *client(struct client_key *key, __u64 now)
{
	struct client_state *st = bpf_map_lookup_elem(&rws_clients, key);
	struct client_state fresh = {};

	if (st)
		return st;
	fresh.win_start = now;
	bpf_map_update_elem(&rws_clients, key, &fresh, BPF_NOEXIST);
	return bpf_map_lookup_elem(&rws_clients, key);
}

/* Меньший из двух потолков; 0 — «без лимита» и в сравнении не участвует. */
static __always_inline __u64 min_rate(__u64 a, __u64 b)
{
	if (!a)
		return b;
	if (!b)
		return a;
	return a < b ? a : b;
}

/*
 * Действующий потолок для пакета; 0 — не резать. Штраф считается только по
 * трафику на портах общего шейпера: это его режим, а не часть мягкой блокировки.
 */
static __always_inline __u64 pick_rate(const struct shaper_cfg *cfg, struct client_state *st,
				       __u64 now, __u32 len, __u64 general, __u64 personal,
				       int on_port)
{
	__u64 rate = min_rate(general, personal);

	if (!on_port || !cfg->pen_bytes)
		return rate;
	if (st->pen_until > now)
		return min_rate(rate, cfg->pen_rate);
	if (now - st->win_start > cfg->pen_window_ns) {
		st->win_start = now;
		st->win_bytes = 0;
	}
	__sync_fetch_and_add(&st->win_bytes, len);
	if (st->win_bytes > cfg->pen_bytes) {
		st->pen_until = now + cfg->pen_duration_ns;
		st->win_start = now;
		st->win_bytes = 0;
		stat_inc(ST_PENALTIES);
		return min_rate(rate, cfg->pen_rate);
	}
	return rate;
}

SEC("tc")
int rws_egress(struct __sk_buff *skb)
{
	struct personal_limit *personal;
	struct client_key key = {};
	struct client_state *st;
	struct shaper_cfg *cfg;
	__u64 now, rate, delay, t, t_next;
	__u32 zero = 0;
	__u16 port;
	int on_port;

	cfg = bpf_map_lookup_elem(&rws_cfg, &zero);
	if (!cfg)
		return TC_ACT_UNSPEC;
	if (!parse(skb, (__u32)cfg->l2_len, 1, &key, &port))
		return TC_ACT_UNSPEC;
	personal = bpf_map_lookup_elem(&rws_personal, &key);
	on_port = bpf_map_lookup_elem(&rws_ports, &port) != NULL;
	barrier_var(on_port);
	if (!personal && !on_port)
		return TC_ACT_UNSPEC;

	now = bpf_ktime_get_ns();
	st = client(&key, now);
	if (!st)
		return TC_ACT_UNSPEC;

	rate = pick_rate(cfg, st, now, skb->len, on_port ? cfg->down_rate : 0,
			 personal ? personal->down_rate : 0, on_port);
	if (!rate)
		return TC_ACT_UNSPEC;

	/* Своё время отправки мог назначить и TCP — берём более позднее */
	t = skb->tstamp;
	if (t < now)
		t = now;
	delay = (__u64)skb->len * NSEC_PER_SEC / rate;
	t_next = st->down_last + delay;
	if (t_next <= t) {
		st->down_last = t;
		return TC_ACT_UNSPEC;
	}
	if (t_next - now >= cfg->horizon_ns) {
		stat_inc(ST_DROPPED_DOWN);
		return TC_ACT_SHOT;
	}
	st->down_last = t_next;
	skb->tstamp = t_next;
	stat_inc(ST_DELAYED);
	return TC_ACT_UNSPEC;
}

SEC("tc")
int rws_ingress(struct __sk_buff *skb)
{
	struct personal_limit *personal;
	struct client_key key = {};
	struct client_state *st;
	struct shaper_cfg *cfg;
	__u64 now, rate, t;
	__u32 zero = 0;
	__u16 port;
	int on_port;

	cfg = bpf_map_lookup_elem(&rws_cfg, &zero);
	if (!cfg)
		return TC_ACT_UNSPEC;
	if (!parse(skb, (__u32)cfg->l2_len, 0, &key, &port))
		return TC_ACT_UNSPEC;
	personal = bpf_map_lookup_elem(&rws_personal, &key);
	on_port = bpf_map_lookup_elem(&rws_ports, &port) != NULL;
	barrier_var(on_port);
	if (!personal && !on_port)
		return TC_ACT_UNSPEC;

	now = bpf_ktime_get_ns();
	st = client(&key, now);
	if (!st)
		return TC_ACT_UNSPEC;

	rate = pick_rate(cfg, st, now, skb->len, on_port ? cfg->up_rate : 0,
			 personal ? personal->up_rate : 0, on_port);
	if (!rate)
		return TC_ACT_UNSPEC;

	t = st->up_next;
	if (t < now)
		t = now;
	if (t - now > cfg->burst_ns) {
		stat_inc(ST_DROPPED_UP);
		return TC_ACT_SHOT;
	}
	st->up_next = t + (__u64)skb->len * NSEC_PER_SEC / rate;
	return TC_ACT_UNSPEC;
}

char LICENSE[] SEC("license") = "Dual MIT/GPL";
