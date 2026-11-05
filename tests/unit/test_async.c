// SPDX-License-Identifier: MIT
#include "dwc2_transport/mock.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define C(x)                                                                                       \
    do {                                                                                           \
        checks++;                                                                                  \
        if (!(x)) {                                                                                \
            fprintf(stderr, "line %d: %s\n", __LINE__, #x);                                        \
            exit(1);                                                                               \
        }                                                                                          \
    } while (0)
static unsigned checks;
static const dt_setup descriptor = {0x80, 6, 0x100, 0, 18};
static void destroy_result(dt_transfer *x, dt_status status, size_t length) {
    const dt_completion *r = dt_transfer_result(x);
    C(r);
    C(r->status == status);
    C(r->actual_length == length);
    C(dt_transfer_free(x, NULL) == DT_OK);
}
int main(void) {
    dt_context *c = NULL, *other = NULL;
    dt_device *d = NULL, *d2 = NULL;
    dt_device_info *list = NULL;
    size_t n = 0, actual = 99;
    dt_error e;
    dt_transfer *x = NULL, *y = NULL, *done = NULL;
    uint8_t buf[18];
    C(dt_context_create("mock", &c, &e) == DT_OK);
    C(dt_context_create("mock", &other, &e) == DT_OK);
    C(dt_enumerate(c, &list, &n, &e) == DT_OK && n == 1);
    C(dt_open(c, list, &d, &e) == DT_OK);
    C(dt_reap(d, 0, &done, &e) == DT_ERROR_AGAIN && done == NULL);
    C(dt_submit_control(d, &descriptor, NULL, 100, (void *)c, &x, &e) == DT_OK);
    C(dt_transfer_result(x) == NULL && dt_transfer_data(x) == NULL);
    C(dt_transfer_free(x, &e) == DT_ERROR_BUSY);
    C(dt_reap(d, 0, &done, &e) == DT_ERROR_AGAIN);
    C(dt_reap(d, 10, &done, &e) == DT_OK && done == x);
    C(dt_transfer_result(x)->user == c);
    C(dt_transfer_data(x)[0] == 18);
    C(dt_cancel(x, &e) == DT_ERROR_NOT_PENDING);
    destroy_result(x, DT_OK, 18);
    C(dt_mock_queue_response(c, &descriptor, DT_ERROR_STALL, NULL, 0, 1000000, &e) == DT_OK);
    C(dt_submit_control(d, &descriptor, NULL, 20, NULL, &x, &e) == DT_OK);
    C(dt_reap(d, 20, &done, &e) == DT_OK);
    destroy_result(done, DT_ERROR_STALL, 0);
    C(dt_mock_set_timing(c, 10000000, 0, &e) == DT_OK);
    C(dt_get_descriptor(d, 1, 0, 0, buf, 18, &actual, &e) == DT_OK && actual == 18);
    dt_setup req = descriptor;
    C(dt_control(d, &req, buf, 1, &actual, &e) == DT_ERROR_TIMEOUT && actual == 0);
    C(dt_submit_control(d, &descriptor, NULL, 2, NULL, &x, &e) == DT_OK);
    uint64_t start = dt_now_ns(c);
    C(dt_reap(d, 1, &done, &e) == DT_ERROR_AGAIN && dt_now_ns(c) == start + 1000000);
    C(dt_reap(d, 2, &done, &e) == DT_OK);
    destroy_result(done, DT_ERROR_TIMEOUT, 0);
    C(dt_submit_control(d, &descriptor, NULL, 0, NULL, &x, &e) == DT_OK);
    C(dt_cancel(x, &e) == DT_OK);
    C(dt_reap(d, 0, &done, &e) == DT_OK);
    destroy_result(done, DT_ERROR_CANCELLED, 0);
    /* Completed before cancel, but giveback delayed: accepted cancel + success.
     */
    C(dt_mock_set_timing(c, 1000000, 3000000, &e) == DT_OK);
    C(dt_submit_control(d, &descriptor, NULL, 2, NULL, &x, &e) == DT_OK);
    C(dt_mock_advance(c, 2000000, &e) == DT_OK);
    C(dt_cancel(x, &e) == DT_OK);
    C(dt_reap(d, 10, &done, &e) == DT_OK);
    destroy_result(done, DT_OK, 18);
    /* A timeout in the same giveback race must also preserve success. */
    C(dt_submit_control(d, &descriptor, NULL, 2, NULL, &x, &e) == DT_OK);
    C(dt_reap(d, 10, &done, &e) == DT_OK);
    destroy_result(done, DT_OK, 18);
    C(dt_mock_set_timing(c, 1000000, 0, &e) == DT_OK);
    C(dt_submit_control(d, &descriptor, NULL, 1, NULL, &x, &e) == DT_OK);
    C(dt_mock_advance(c, 2000000, &e) == DT_OK);
    C(dt_cancel(x, &e) == DT_ERROR_NOT_PENDING);
    C(dt_reap(d, 0, &done, &e) == DT_OK);
    destroy_result(done, DT_OK, 18);
    /* Completion order follows device latency, not submission order. */
    C(dt_mock_queue_response(c, &descriptor, DT_OK, buf, 18, 3000000, &e) == DT_OK);
    C(dt_submit_control(d, &descriptor, NULL, 10, NULL, &x, &e) == DT_OK);
    C(dt_submit_control(d, &descriptor, NULL, 10, NULL, &y, &e) == DT_OK);
    C(dt_reap(d, 10, &done, &e) == DT_OK && done == y);
    destroy_result(done, DT_OK, 18);
    C(dt_reap(d, 10, &done, &e) == DT_OK && done == x);
    destroy_result(done, DT_OK, 18);
    C(dt_submit_endpoint(d, 0, DT_TRANSFER_BULK, 0x81, NULL, 64, 10, NULL, &x, &e) ==
      DT_ERROR_INVALID);
    C(dt_claim_interface(d, 0, 0, &e) == DT_OK);
    C(dt_submit_endpoint(d, 0, DT_TRANSFER_INTERRUPT, 0x80, NULL, 64, 10, NULL, &x, &e) ==
      DT_ERROR_INVALID);
    C(dt_submit_endpoint(d, 0, DT_TRANSFER_BULK, 0x81, NULL, 64, 2, NULL, &x, &e) == DT_OK);
    C(dt_release_interface(d, 0, &e) == DT_ERROR_BUSY);
    C(dt_reset(d, &e) == DT_ERROR_BUSY);
    C(dt_reap(d, 10, &done, &e) == DT_OK);
    destroy_result(done, DT_ERROR_TIMEOUT, 0);
    uint8_t payload[] = {1, 2, 3};
    C(dt_mock_queue_response(c, NULL, DT_OK, payload, 3, 1000000, &e) == DT_OK);
    payload[0] = 99;
    C(dt_submit_endpoint(d, 0, DT_TRANSFER_BULK, 0x81, NULL, 64, 5, NULL, &x, &e) == DT_OK);
    C(dt_reap(d, 10, &done, &e) == DT_OK && dt_transfer_data(done)[0] == 1);
    destroy_result(done, DT_OK, 3);
    C(dt_mock_queue_response(c, NULL, DT_OK, NULL, 0, 1000000, &e) == DT_OK);
    C(dt_submit_endpoint(d, 0, DT_TRANSFER_BULK, 1, payload, 3, 5, NULL, &x, &e) == DT_OK);
    payload[0] = 42;
    C(dt_reap(d, 10, &done, &e) == DT_OK && dt_transfer_data(done)[0] == 99);
    destroy_result(done, DT_OK, 3);
    C(dt_release_interface(d, 0, &e) == DT_OK);
    /* Disconnect drains results; reconnection never resurrects an old handle. */
    C(dt_submit_control(d, &descriptor, NULL, 10, NULL, &x, &e) == DT_OK);
    C(dt_mock_set_connected(c, 0, &e) == DT_OK);
    C(dt_reap(d, 0, &done, &e) == DT_OK);
    destroy_result(done, DT_ERROR_NO_DEVICE, 0);
    dt_device_info *empty = NULL;
    C(dt_enumerate(c, &empty, &n, &e) == DT_OK && n == 0 && empty == NULL);
    C(dt_mock_set_connected(c, 1, &e) == DT_OK);
    C(dt_get_descriptor(d, 1, 0, 0, buf, 18, &actual, &e) == DT_ERROR_NO_DEVICE);
    C(dt_open(c, list, &d2, &e) == DT_OK);
    C(dt_get_descriptor(d2, 1, 0, 0, buf, 18, &actual, &e) == DT_OK);
    dt_close(d);
    d = d2;
    /* Separate context is independent of connection and virtual time. */
    C(dt_now_ns(other) == 0);
    C(dt_enumerate(other, &empty, &n, &e) == DT_OK && n == 1);
    dt_device_list_free(empty);
    /* Bounded resource pool and close with unreaped objects. ASan verifies
     * cleanup. */
    for (unsigned i = 0; i < 64; i++)
        C(dt_submit_control(d, &descriptor, NULL, 0, NULL, &x, &e) == DT_OK);
    C(dt_submit_control(d, &descriptor, NULL, 0, NULL, &x, &e) == DT_ERROR_BUSY && x == NULL);
    dt_close(d);
    C(dt_open(c, list, &d, &e) == DT_OK);
    C(dt_submit_control(d, &descriptor, NULL, 0, NULL, &x, &e) == DT_OK);
    dt_device_list_free(list);
    dt_context_destroy(c);
    dt_context_destroy(other);
    printf("async: %u checks PASS\n", checks);
    return 0;
}
