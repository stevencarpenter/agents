#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "stackq.h"

/* stackq API (see stackq.h):
 *   stackq *stackq_create(size_t capacity);
 *   int     stackq_push(stackq *q, const void *item, size_t len);
 *   int     stackq_pop(stackq *q, void *out, size_t out_cap, size_t *out_len);
 *   void    stackq_destroy(stackq *q);
 */

static void test_push_pop(void)
{
    stackq *q = stackq_create(4);
    char out[16];
    size_t n = 0;

    stackq_push(q, "abc", 3);
    stackq_pop(q, out, sizeof out, &n);
    printf("popped %zu bytes\n", n);
    assert(n > 0);
}

static void test_push_pop_again(void)
{
    stackq *q = stackq_create(4);
    char out[16];
    size_t n = 0;

    stackq_push(q, "xyz", 3);
    stackq_pop(q, out, sizeof out, &n);
    assert(n > 0);
}

static void test_many(void)
{
    stackq *q = stackq_create(1000);
    for (int i = 0; i < 1000; i++) {
        int rc = stackq_push(q, &i, sizeof i);
        assert(rc == 0);
    }
    stackq_destroy(q);
}

int main(void)
{
    test_push_pop();
    test_push_pop_again();
    test_many();
    printf("all tests passed\n");
    return 0;
}
