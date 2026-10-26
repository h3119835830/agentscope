/* Read-only compiled matcher probe. No loader, ptrace, shell, or BPF syscalls.
 * Build against the exact ActPlane header used by the local compiler. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <arpa/inet.h>
#include "taint.h"

static int target_matches(unsigned int op, unsigned int match, const char *pattern,
                          unsigned int ipv4, unsigned int mask, const char *sample)
{
    char padded[TAINT_TEXT_BUF] = {0};
    memcpy(padded, sample, strlen(sample));
    if (op == TOP_CONNECT || op == TOP_RECV) {
        struct in_addr address;
        if (inet_pton(AF_INET, sample, &address) != 1) return 0;
        return (address.s_addr & mask) == (ipv4 & mask);
    }
    return op == TOP_EXEC ? taint_exec_match(match, padded, pattern) : taint_match(match, padded, pattern);
}

int main(int argc, char **argv)
{
    if (argc != 5 || strlen(argv[3]) >= TAINT_PAT_LEN || strlen(argv[4]) >= TAINT_ARG_LEN) return 2;
    char *end;
    unsigned long operation = strtoul(argv[2], &end, 10);
    if (*end || operation > TOP_RECV) return 2;
    FILE *input = fopen(argv[1], "rb");
    struct taint_config *config = calloc(1, sizeof(*config));
    if (!input || !config) return 3;
    size_t count = fread(config, 1, sizeof(*config), input);
    int extra = fgetc(input);
    fclose(input);
    if (count != sizeof(*config) || extra != EOF || config->n_rules > MAX_TAINT_RULES || config->n_updates > MAX_TAINT_UPDATES) return 4;
    unsigned int sinks=0, invalidators=0, sources=0;
    for (unsigned int i=0; i<config->n_rules; i++) {
        struct taint_rule *r = &config->rules[i];
        if (r->op != operation || !target_matches(r->op,r->match,r->target,r->ipv4,r->ipv4_mask,argv[3])) continue;
        if (r->arg[0] && strcmp(r->arg,argv[4])) continue;
        /* Mirror the engine's target exception using the same compiled fields.
         * Historical/lineage conditions are deliberately outside this probe. */
        if (r->cond_kind == TCOND_TARGET) {
            int allowed = target_matches(r->op,r->cond_match,r->cond_pat,
                                         r->cond_ipv4,r->cond_ipv4_mask,argv[3]);
            if (r->cond_neg) allowed = !allowed;
            if (allowed) continue;
        }
        sinks++;
    }
    for (unsigned int i=0; i<config->n_updates; i++) {
        struct taint_update *u = &config->updates[i];
        if (u->op != operation || !target_matches(u->op,u->match,u->target,u->ipv4,u->ipv4_mask,argv[3])) continue;
        if (u->arg[0] && strcmp(u->arg,argv[4])) continue;
        invalidators += u->invals != 0;
        sources += u->add != 0;
    }
    printf("{\"target\":%u,\"invalidation\":%u,\"source\":%u}\n",sinks,invalidators,sources);
    free(config);
    return 0;
}
