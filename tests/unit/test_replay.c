// SPDX-License-Identifier: MIT
#include "dwc2_transport/mock.h"
#include <stdio.h>
#include <string.h>
int main(int argc, char **argv) {
    dt_context *c = NULL;
    dt_device_info *list = NULL;
    dt_device *d = NULL;
    size_t n, actual;
    dt_error e;
    if (argc != 3)
        return 2;
    if (dt_context_create("mock", &c, &e))
        goto fail;
    if (dt_mock_load_replay(c, argv[2], &e) != DT_ERROR_INVALID)
        goto fail;
    if (dt_mock_load_replay(c, argv[1], &e) || dt_enumerate(c, &list, &n, &e) ||
        dt_open(c, list, &d, &e))
        goto fail;
    for (unsigned i = 0; i < 8; i++) {
        uint8_t b[18];
        if (dt_get_descriptor(d, 1, 0, 0, b, sizeof(b), &actual, &e) || actual != 18 ||
            b[8] != 0x86 || b[9] != 0x1a || b[10] != 0x23 || b[11] != 0x75)
            goto fail;
    }
    if (dt_now_ns(c) != 5166982) {
        fprintf(stderr, "replay time %llu\n", (unsigned long long)dt_now_ns(c));
        goto fail;
    }
    dt_device_list_free(list);
    dt_context_destroy(c);
    puts("HostLab descriptor replay PASS");
    return 0;
fail:
    fprintf(stderr, "replay failed: %s %s\n", e.operation, e.message);
    dt_device_list_free(list);
    dt_context_destroy(c);
    return 1;
}
