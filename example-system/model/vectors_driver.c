/* Replay golden vectors through the C filter. One integer sample per stdin line; prints the
 * filtered value per line. Built and run by run_vectors.py --impl c; not part of the firmware. */
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>

#include "../src/filter.h"

int main(void) {
    filter_t f;
    filter_init(&f);
    char line[64];
    while (fgets(line, sizeof line, stdin)) {
        char *end;
        errno = 0;
        long v = strtol(line, &end, 10);
        if (end == line || errno != 0 || v < INT16_MIN || v > INT16_MAX) {
            fprintf(stderr, "bad sample: %s", line);
            return 1;
        }
        printf("%d\n", (int)filter_update(&f, (int16_t)v));
    }
    return 0;
}
