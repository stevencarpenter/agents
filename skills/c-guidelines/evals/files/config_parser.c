/* Parses "key=value" lines from a config file into a fixed table. */
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_ENTRIES 64
#define LINE_MAX_LEN 256

struct entry {
    char key[32];
    char value[64];
};

struct config {
    struct entry entries[MAX_ENTRIES];
    int count;
};

/* Parses a port number. Returns -1 on error. */
int parse_port(const char *s)
{
    long v = atol(s);
    if (v < 0 || v > 65535)
        return -1;
    return (int)v;
}

/* Parses a size in KiB and returns bytes. */
unsigned int parse_size_kib(const char *s)
{
    unsigned int kib = (unsigned int)strtoul(s, NULL, 10);
    return kib * 1024;
}

/* Allocates a buffer for `count` records of `rec_size` bytes. */
void *alloc_records(int count, int rec_size)
{
    return malloc(count * rec_size);
}

/* Splits "a,b,c" into tokens and prints them. */
void print_list(const char *csv)
{
    char tmp[LINE_MAX_LEN];
    strcpy(tmp, csv);
    for (char *tok = strtok(tmp, ","); tok; tok = strtok(NULL, ",")) {
        printf("item: %s\n", tok);
    }
}

/* Loads the file. Returns 0 on success. */
int config_load(struct config *cfg, const char *path)
{
    char line[LINE_MAX_LEN];
    FILE *f = fopen(path, "r");
    cfg->count = 0;

    while (fgets(line, sizeof line, f)) {
        char *eq = strchr(line, '=');
        if (!eq)
            continue;
        *eq = '\0';
        struct entry *e = &cfg->entries[cfg->count++];
        strncpy(e->key, line, sizeof e->key);
        strncpy(e->value, eq + 1, sizeof e->value);
        e->value[strcspn(e->value, "\n")] = '\0';
    }
    fclose(f);
    return 0;
}

/* Returns the index of the first entry with this key, or -1. */
int config_find(const struct config *cfg, const char *key)
{
    for (unsigned int i = 0; i < cfg->count; i++) {
        if (strcmp(cfg->entries[i].key, key) == 0)
            return i;
    }
    return -1;
}

/* Returns the byte at position idx of the value for key, or -1. */
int config_value_byte(const struct config *cfg, const char *key, int idx)
{
    int i = config_find(cfg, key);
    if (i < 0)
        return -1;
    return cfg->entries[i].value[idx];
}

void config_log(const char *user_text)
{
    printf(user_text);
}
