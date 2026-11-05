// SPDX-License-Identifier: MIT
/* Test the real diagnostic inspector against deterministic USB responses. */
int diag_cli_test_main(int argc, char **argv);
#define main diag_cli_test_main
#include "../../tools/cli.c"
#undef main
#include "dwc2_transport/mock.h"
#define C(x)                                                                                       \
    do {                                                                                           \
        if (!(x)) {                                                                                \
            fprintf(stderr, "line %d: %s\n", __LINE__, #x);                                        \
            exit(1);                                                                               \
        }                                                                                          \
    } while (0)
static void response(dt_context *c, uint16_t value, uint16_t language, const uint8_t *b, size_t n,
                     uint16_t requested) {
    dt_setup s = {0x80, 6, value, language, requested};
    C(dt_mock_queue_response(c, &s, DT_OK, b, (uint32_t)n, 1000, NULL) == DT_OK);
}
int main(int argc, char **argv) {
    dt_context *c = NULL;
    dt_device *d = NULL;
    dt_device_info *list = NULL;
    size_t n;
    C(argc == 2);
    C(dt_context_create("mock", &c, NULL) == DT_OK);
    C(dt_enumerate(c, &list, &n, NULL) == DT_OK);
    C(dt_open(c, list, &d, NULL) == DT_OK);
    uint8_t desc[18] = {18, 1, 0, 2, 0, 0, 0, 64, 9, 0x12, 1, 0, 0, 1, 1, 2, 3, 1};
    if (!strcmp(argv[1], "alias"))
        desc[14] = 3;
    response(c, 0x100, 0, desc, 18, 18);
    if (!strcmp(argv[1], "malformed")) {
        uint8_t bad[32] = {9, 2, 32, 0, 1,    1, 0,  0x80, 50, 9, 4, 0, 0, 3,  0xff, 0,
                           0, 0, 7,  5, 0x81, 2, 64, 0,    0,  7, 5, 1, 2, 64, 0,    0};
        response(c, 0x200, 0, bad, 9, 9);
        response(c, 0x200, 0, bad, 32, 32);
    }

    uint8_t language[] = {4, 3, 9, 4}, maker[] = {4, 3, 'M', 0}, product[] = {4, 3, 'P', 0};
    uint8_t secret[] = {18, 3, 'S', 0, 'E', 0, 'C', 0, 'R', 0, 'E', 0, 'T', 0, '4', 0, '2', 0};
    if (strcmp(argv[1], "missing")) {
        response(c, 0x300, 0, language, 4, 255);
        if (!strcmp(argv[1], "timeout")) {
            dt_setup slow = {0x80, 6, 0x301, 0x409, 255};
            C(dt_mock_queue_response(c, &slow, DT_OK, maker, 4, 2000000000, NULL) == DT_OK);
        } else
            response(c, 0x301, 0x409, maker, 4, 255);
        response(c, 0x302, 0x409, product, 4, 255);
        response(c, 0x303, 0x409, secret, sizeof(secret), 255);
    }
    int include = !strcmp(argv[1], "include");
    int result = inspect(d, 1, include);
    if (strcmp(argv[1], "missing") && !include) {
        uint8_t b[255];
        size_t actual = 0;
        C(dt_get_descriptor(d, 3, 3, 0x409, b, 255, &actual, NULL) == DT_OK &&
          actual == sizeof(secret));
        C(!memcmp(b, secret, sizeof(secret))); /* Inspector never requested it. */
    }
    dt_device_list_free(list);
    dt_context_destroy(c);
    return result;
}
