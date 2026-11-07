/* Byte buffer module used by a packet decoder. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    char *data;
    int len;
    int cap;
} buffer_t;

buffer_t *buffer_new(int cap)
{
    buffer_t *b = malloc(sizeof(buffer_t));
    b->data = malloc(cap);
    b->len = 0;
    b->cap = cap;
    return b;
}

/* Appends n bytes. */
void buffer_append(buffer_t *b, const char *src, int n)
{
    if (b->len + n > b->cap) {
        b->cap = (b->len + n) * 2;
        b->data = realloc(b->data, b->cap);
    }
    memcpy(b->data + b->len, src, n);
    b->len += n;
}

/* Returns a copy of the buffer as a C string. */
char *buffer_to_string(buffer_t *b)
{
    char *s = malloc(b->len);
    memcpy(s, b->data, b->len);
    return s;
}

/* Reads a length-prefixed record: 2 byte big-endian length, then payload. */
int buffer_read_record(buffer_t *b, int offset, char *out)
{
    unsigned short rec_len = (b->data[offset] << 8) | b->data[offset + 1];
    memcpy(out, b->data + offset + 2, rec_len);
    out[rec_len] = '\0';
    return rec_len;
}

/* Builds a label like "pkt-<name>" into a fixed buffer. */
void buffer_label(buffer_t *b, const char *name, char *label)
{
    strcpy(label, "pkt-");
    strcat(label, name);
    sprintf(label + strlen(label), ":%d", b->len);
}

/* Allocates a table of n entries of entry_size bytes. */
void *buffer_table(unsigned int n, unsigned int entry_size)
{
    return malloc(n * entry_size);
}

void buffer_free(buffer_t *b)
{
    free(b->data);
    free(b);
    b->data = NULL;
}

int buffer_dump(buffer_t *b, const char *path)
{
    FILE *f = fopen(path, "wb");
    fwrite(b->data, 1, b->len, f);
    fclose(f);
    return 0;
}
