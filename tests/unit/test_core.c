// SPDX-License-Identifier: MIT
#include "dwc2_transport/transport.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x)                                                                                   \
    do {                                                                                           \
        if (!(x)) {                                                                                \
            fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x);                                \
            exit(1);                                                                               \
        }                                                                                          \
    } while (0)
int main(void) {
    dt_context *c = NULL, *other = NULL;
    dt_device_info *list = NULL;
    dt_device *d = NULL, *d2 = NULL;
    size_t n = 0, actual = 0;
    uint8_t b[32];
    dt_error e;
    CHECK(dt_api_version() == 0x10000);
    CHECK(!strcmp(dt_version(), DT_VERSION));
    CHECK(dt_context_create("bad", &c, &e) == DT_ERROR_UNSUPPORTED && c == NULL);
    CHECK(dt_context_create("mock", &c, &e) == DT_OK);
    CHECK(dt_context_create("mock", &other, NULL) == DT_OK);
    CHECK(dt_enumerate(c, &list, &n, &e) == DT_OK && n == 1);
    CHECK(list[0].vendor_id == 0x1209);
    CHECK(dt_open(c, list, &d, &e) == DT_OK);
    CHECK(dt_open(c, list, &d2, NULL) == DT_OK);
    CHECK(dt_get_descriptor(d, 1, 0, 0, b, 18, &actual, &e) == DT_OK && actual == 18 && b[1] == 1);
    CHECK(dt_get_descriptor(d, 2, 0, 0, b, 32, &actual, &e) == DT_OK && actual == 32 && b[1] == 2);
    CHECK(dt_get_descriptor(d, 3, 1, 0, b, 32, &actual, &e) == DT_ERROR_STALL && actual == 0);
    CHECK(dt_get_descriptor(d, 1, 0, 0, NULL, 18, &actual, &e) == DT_ERROR_INVALID);
    CHECK(dt_claim_interface(d, 0, 0, &e) == DT_OK);
    CHECK(dt_claim_interface(d2, 0, 0, &e) == DT_ERROR_BUSY);
    CHECK(dt_reset(d, &e) == DT_ERROR_BUSY);
    CHECK(dt_release_interface(d, 0, &e) == DT_OK);
    CHECK(dt_reset(d, &e) == DT_OK);
    CHECK(dt_capabilities(d) & DT_CAP_CONTROL);
    dt_close(d);
    dt_device_list_free(list);
    dt_context_destroy(c);
    dt_context_destroy(other);
    puts("core: discovery/open/descriptor/close and ownership PASS");
    return 0;
}
