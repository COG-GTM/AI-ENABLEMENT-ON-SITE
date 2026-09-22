/* Minimal test harness: no framework to install, works with any C99/C11 compiler.
 * If your tree already has GoogleTest, Unity, CppUTest or Ceedling, use that instead and keep
 * only hal_stub.[ch] from this template. */
#ifndef HOST_HARNESS_H
#define HOST_HARNESS_H

#include <stdio.h>

static int harness_failures = 0;
static int harness_checks = 0;

#define CHECK(cond)                                                       \
    do {                                                                  \
        harness_checks++;                                                 \
        if (!(cond)) {                                                    \
            harness_failures++;                                           \
            printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #cond);         \
        }                                                                 \
    } while (0)

#define CHECK_EQ_INT(a, b)                                                             \
    do {                                                                               \
        long long _a = (long long)(a), _b = (long long)(b);                            \
        harness_checks++;                                                              \
        if (_a != _b) {                                                                \
            harness_failures++;                                                        \
            printf("FAIL %s:%d %s == %s  (%lld != %lld)\n", __FILE__, __LINE__, #a, #b, _a, _b); \
        }                                                                              \
    } while (0)

#define RUN(test)                    \
    do {                             \
        hal_stub_reset();            \
        printf("  %s\n", #test);     \
        test();                      \
    } while (0)

static inline int harness_report(void) {
    if (harness_failures) {
        printf("%d of %d check(s) failed\n", harness_failures, harness_checks);
        return 1;
    }
    printf("host tests: %d checks passed\n", harness_checks);
    return 0;
}

#endif
