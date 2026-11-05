// SPDX-License-Identifier: MIT
#include "dwc2_transport/transport.h"
#include <stdio.h>
#include <string.h>
int main(int argc, char **argv) {
    dt_context *c = NULL;
    dt_device *d = NULL;
    dt_device_info *list = NULL;
    size_t count = 0, actual = 0;
    uint8_t b[18];
    dt_error e;
    int rc = 1;
    const char *backend = argc > 1 && !strcmp(argv[1], "--mock") ? "mock" : "linux-usbfs";
    const char *path = argc > 1 && strcmp(argv[1], "--mock") ? argv[1] : NULL;
    if (dt_context_create(backend, &c, &e) || dt_enumerate(c, &list, &count, &e))
        goto fail;
    for (size_t i = 0; i < count; i++) {
        if ((path && strcmp(list[i].path, path)) || (!path && list[i].device_class == 9))
            continue;
        if (dt_open(c, &list[i], &d, &e) ||
            dt_get_descriptor(d, 1, 0, 0, b, sizeof(b), &actual, &e))
            goto fail;
        printf("%04x:%04x descriptor:", list[i].vendor_id, list[i].product_id);
        for (size_t j = 0; j < actual; j++)
            printf("%02x", b[j]);
        puts("");
        rc = actual == 18 ? 0 : 1;
        goto done;
    }
    fprintf(stderr, "no matching non-hub device\n");
    goto done;
fail:
    fprintf(stderr, "%s: %s (%s)\n", e.operation, e.message, dt_status_name(e.status));
done:
    dt_close(d);
    dt_device_list_free(list);
    dt_context_destroy(c);
    return rc;
}
