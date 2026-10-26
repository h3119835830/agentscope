/* Read an isolated compiler artifact and call the unchanged pure matcher.
 * This is not a BPF loader and does not observe or affect running processes. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "taint.h"

int main(int argc, char **argv)
{
    if (argc != 3 || strlen(argv[2]) >= TAINT_PAT_LEN) return 2;
    struct taint_config *config = calloc(1, sizeof(*config));
    FILE *input = fopen(argv[1], "rb");
    if (!input || !config) return 3;
    size_t count = fread(config, 1, sizeof(*config), input);
    int extra = fgetc(input);
    fclose(input);
    if (count != sizeof(*config) || extra != EOF || config->n_updates > MAX_TAINT_UPDATES) return 4;
    char path[TAINT_PAT_LEN] = {0};
    memcpy(path, argv[2], strlen(argv[2]));
    unsigned int matched = 0, invalidators = 0;
    for (unsigned int index = 0; index < config->n_updates; index++) {
        struct taint_update *update = &config->updates[index];
        if (!update->invals) continue;
        invalidators++;
        matched += taint_match(update->match, path, update->target) != 0;
    }
    printf("{\"invalidators\":%u,\"matched\":%u}\n", invalidators, matched);
    free(config);
    return 0;
}
