/* SPDX-License-Identifier: GPL-2.0 OR BSD-3-Clause */
#ifndef __FLOW_TRACE_BPF_H
#define __FLOW_TRACE_BPF_H
/* Audit-only witness heads. Failure never changes enforcement decisions.
 * Node identity includes kernel process birth time / inode generation.
 * Missing identities are explicitly incomplete, never joined by display path. */
struct flow_node {
	__u64 birth;
	__u64 ino;
	__u32 kind;
	__u32 pid;
	__u32 dev;
	__u32 generation;
};
struct flow_key {
	struct flow_node node;
	__u64 label;
	__u32 domain;
	__u32 pad;
};
struct flow_event {
	__u32 type;
	__u32 operation;
	__u64 id;
	__u64 predecessor;
	__u64 timestamp_ns;
	__u64 label;
	__u64 lost;
	__u64 tool_call_tag;
	struct flow_node from;
	struct flow_node to;
	__u32 domain;
	__u32 process_domain;
	__u32 flags; /* 1 root source, 2 incomplete identity/predecessor */
	__u32 rule_id;
	__u32 outcome; /* 0 propagation, 1 report, 2 block, 3 kill */
	__u32 pad;
	char hook[64];
	char target[MAX_FILENAME_LEN];
};
struct flow_hook_name { char value[64]; };
struct {
	__uint(type, BPF_MAP_TYPE_RINGBUF);
	__uint(max_entries, 4 * 1024 * 1024);
} flow_rb SEC(".maps");
struct {
	__uint(type, BPF_MAP_TYPE_LRU_HASH);
	__uint(max_entries, 32768);
	__type(key, struct flow_key);
	__type(value, __u64);
} flow_heads SEC(".maps");
struct {
	__uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
	__uint(max_entries, 1);
	__type(key, __u32);
	__type(value, struct flow_key);
} flow_key_tmp SEC(".maps");
struct {
	__uint(type, BPF_MAP_TYPE_ARRAY);
	__uint(max_entries, 2);
	__type(key, __u32);
	__type(value, __u64);
} flow_counters SEC(".maps");
struct {
	__uint(type, BPF_MAP_TYPE_LRU_HASH);
	__uint(max_entries, 16384);
	__type(key, __u32);
	__type(value, __u64);
} flow_births SEC(".maps");
struct {
	__uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
	__uint(max_entries, 1);
	__type(key, __u32);
	__type(value, struct flow_hook_name);
} flow_hooks SEC(".maps");
struct flow_ctx {
	struct flow_node from, to;
	__u64 labels;
	__u32 domain, operation, flags, rule_id, outcome;
	char target[MAX_FILENAME_LEN];
};
struct {
	__uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
	__uint(max_entries, 1);
	__type(key, __u32);
	__type(value, struct flow_ctx);
} flow_ctx_tmp SEC(".maps");

static __always_inline struct flow_ctx *flow_begin(void)
{
	__u32 zero = 0;
	struct flow_ctx *ctx = bpf_map_lookup_elem(&flow_ctx_tmp, &zero);
	if (ctx)
		__builtin_memset(ctx, 0, sizeof(*ctx));
	return ctx;
}
static __always_inline void flow_target(struct flow_ctx *ctx, const char *target)
{
	if (target)
		bpf_probe_read_kernel_str(ctx->target, sizeof(ctx->target), target);
}

static __always_inline void flow_set_hook(const char *hook)
{
	__u32 k = 0;
	struct flow_hook_name *value = bpf_map_lookup_elem(&flow_hooks, &k);
	if (value)
		bpf_probe_read_kernel_str(value->value, sizeof(value->value), hook);
}
static __noinline __u64 flow_birth(__u32 pid)
{
	/* Fork records the child before propagation; every other caller supplies
	 * its current TGID. Exit removes this cache before PID reuse. */
	__u64 *birth = bpf_map_lookup_elem(&flow_births, &pid);
	if (birth)
		return *birth;
	struct task_struct *task = (void *)bpf_get_current_task();
	struct task_struct *leader = BPF_CORE_READ(task, group_leader);
	__u64 value = BPF_CORE_READ(leader, start_boottime);
	bpf_map_update_elem(&flow_births, &pid, &value, BPF_ANY);
	return value;
}
static __always_inline struct flow_node flow_process(__u32 pid)
{
	struct flow_node node = { .kind = 1, .pid = pid, .birth = flow_birth(pid) };
	return node;
}
static __always_inline struct flow_node flow_file(struct file_id *fid)
{
	struct flow_node node = { .kind = 2, .ino = fid->ino, .dev = fid->dev,
				 .generation = fid->_pad };
	return node;
}
static int flow_emit_cb(__u32 i, void *arg)
{
	(void)arg;
	__u32 zero = 0, one = 1;
	struct flow_ctx *c = bpf_map_lookup_elem(&flow_ctx_tmp, &zero);
	if (!c)
		return 1;
	if (i >= MAX_TAINT_LABELS)
		return 1;
	__u64 bit = 1ULL << i;
	if (!(c->labels & bit))
		return 0;
	__u64 *sequence = bpf_map_lookup_elem(&flow_counters, &zero);
	__u64 *lost = bpf_map_lookup_elem(&flow_counters, &one);
	if (!sequence || !lost)
		return 0;
	__u64 id = __sync_fetch_and_add(sequence, 1) + 1;
	struct flow_key *key = bpf_map_lookup_elem(&flow_key_tmp, &zero);
	if (!key)
		return 0;
	__builtin_memset(key, 0, sizeof(*key));
	key->node = c->from;
	key->label = bit;
	key->domain = c->domain;
	__u64 *head = bpf_map_lookup_elem(&flow_heads, key);
	__u64 predecessor = head ? *head : 0;
	struct flow_event *event = bpf_ringbuf_reserve(&flow_rb, sizeof(*event), 0);
	if (!event) {
		__sync_fetch_and_add(lost, 1);
		/* Record the missing predecessor ID so a later edge cannot skip it. */
		key->node = c->to;
		if (c->outcome == 0)
			bpf_map_update_elem(&flow_heads, key, &id, BPF_ANY);
		return 0;
	}
	__builtin_memset(event, 0, sizeof(*event));
	event->type = 4;
	event->operation = c->operation;
	event->id = id;
	event->predecessor = (c->flags & 1) ? 0 : predecessor;
	event->timestamp_ns = bpf_ktime_get_ns();
	event->label = bit;
	event->lost = *lost;
	event->from = c->from;
	event->to = c->to;
	event->domain = c->domain;
	__u32 pid = c->from.kind == 1 ? c->from.pid : c->to.pid;
	event->process_domain = cap_domain_for_pid(pid);
	struct flow_hook_name *hook = bpf_map_lookup_elem(&flow_hooks, &zero);
	if (hook)
		__builtin_memcpy(event->hook, hook->value, sizeof(event->hook));
	event->flags = c->flags;
	if (!(c->flags & 1) && !predecessor)
		event->flags |= 2;
	if (!event->hook[0] || (c->from.kind == 1 && !c->from.birth) ||
	    (c->to.kind == 1 && !c->to.birth) ||
	    (c->from.kind == 2 && (!c->from.dev || !c->from.generation)) ||
	    (c->to.kind == 2 && (!c->to.dev || !c->to.generation)))
		event->flags |= 2;
	event->rule_id = c->rule_id;
	event->outcome = c->outcome;
	__u64 *tag = bpf_map_lookup_elem(&audit_call, &pid);
	event->tool_call_tag = tag ? *tag : 0;
	__builtin_memcpy(event->target, c->target, sizeof(event->target));
	bpf_ringbuf_submit(event, 0);
	if (c->outcome == 0) {
		key->node = c->to;
		if (bpf_map_update_elem(&flow_heads, key, &id, BPF_ANY))
			__sync_fetch_and_add(lost, 1);
	}
	return 0;
}
static __noinline void flow_emit(void)
{
	bpf_loop(MAX_TAINT_LABELS, flow_emit_cb, 0, 0);
}
#endif
