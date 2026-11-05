// SPDX-License-Identifier: MIT
/* Bounded, conventional tests. Endpoint tests explicitly limited to CH340 IN.
 */
#include "dwc2_transport/transport.h"
#include <dirent.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
static unsigned failures, checks;
static void check(const char *name, int pass, dt_status s, int raw, size_t actual) {
    checks++;
    if (!pass)
        failures++;
    printf("{\"test\":\"%s\",\"pass\":%s,\"status\":\"%s\",\"kernel_status\":%d,"
           "\"actual\":%zu}\n",
           name, pass ? "true" : "false", dt_status_name(s), raw, actual);
    fflush(stdout);
}
static int fd_count(void) {
    DIR *dir = opendir("/proc/self/fd");
    struct dirent *de;
    int n = 0;
    if (!dir)
        return -1;
    while ((de = readdir(dir)))
        if (de->d_name[0] != '.')
            n++;
    closedir(dir);
    return n;
}
static volatile sig_atomic_t stop_requested;
static void signal_stop(int sig) {
    (void)sig;
    stop_requested = 1;
}
int main(int argc, char **argv) {
    dt_context *c = NULL;
    dt_device_info *list = NULL;
    dt_device *d = NULL;
    size_t count = 0, actual = 0;
    dt_error e;
    dt_status s = DT_OK;
    uint8_t b[18];
    dt_setup setup = {0x80, 6, 0x100, 0, 18};
    dt_transfer *x = NULL, *done = NULL;
    int endpoint = 0, reset = 0, hold = 0;
    if (argc < 2) {
        fprintf(stderr, "usage: test-hardware PATH [--ch340-in] [--reset] [--hold]\n");
        return 2;
    }
    for (int i = 2; i < argc; i++) {
        if (!strcmp(argv[i], "--ch340-in"))
            endpoint = 1;
        else if (!strcmp(argv[i], "--reset"))
            reset = 1;
        else if (!strcmp(argv[i], "--hold"))
            hold = 1;
        else
            return 2;
    }
    int before = fd_count();
    s = dt_context_create("linux-usbfs", &c, &e);
    if (s)
        goto fatal;
    s = dt_enumerate(c, &list, &count, &e);
    if (s)
        goto fatal;
    const dt_device_info *info = NULL;
    for (size_t i = 0; i < count; i++)
        if (!strcmp(list[i].path, argv[1]))
            info = &list[i];
    if (!info || info->device_class == 9) {
        fprintf(stderr, "non-hub target required\n");
        goto fatal;
    }
    if (endpoint && (info->vendor_id != 0x1a86 || info->product_id != 0x7523)) {
        fprintf(stderr, "endpoint profile only for CH340\n");
        goto fatal;
    }
    check("discovery", 1, DT_OK, 0, 0);
    s = dt_open(c, info, &d, &e);
    if (s)
        goto fatal;
    for (unsigned i = 0; i < 50; i++) {
        s = dt_get_descriptor(d, 1, 0, 0, b, 18, &actual, &e);
        check("sync_descriptor", s == DT_OK && actual == 18, s, 0, actual);
    }
    for (unsigned i = 0; i < 25; i++) {
        s = dt_submit_control(d, &setup, NULL, 1000, NULL, &x, &e);
        if (s)
            goto fatal;
        s = dt_reap(d, 1500, &done, &e);
        if (s)
            goto fatal;
        const dt_completion *r = dt_transfer_result(done);
        check("async_descriptor", r->status == DT_OK && r->actual_length == 18, r->status,
              r->kernel_status, r->actual_length);
        (void)dt_transfer_free(done, NULL);
    }
    for (unsigned i = 0; i < 25; i++) {
        s = dt_submit_control(d, &setup, NULL, 1000, NULL, &x, &e);
        if (s)
            goto fatal;
        dt_status cancel = dt_cancel(x, &e);
        check("control_cancel_request", cancel == DT_OK || cancel == DT_ERROR_NOT_PENDING, cancel,
              e.system_errno, 0);
        s = dt_reap(d, 1500, &done, &e);
        if (s)
            goto fatal;
        const dt_completion *r = dt_transfer_result(done);
        check("control_cancel_result", r->status == DT_OK || r->status == DT_ERROR_CANCELLED,
              r->status, r->kernel_status, r->actual_length);
        (void)dt_transfer_free(done, NULL);
    }
    if (endpoint) {
        s = dt_claim_interface(d, 0, 1, &e);
        check("claim_ch340", s == DT_OK, s, e.system_errno, 0);
        if (s)
            goto fatal;
        for (unsigned i = 0; i < 5; i++) {
            s = dt_submit_endpoint(d, 0, DT_TRANSFER_BULK, 0x82, NULL, 64, 1000, NULL, &x, &e);
            if (s)
                goto fatal;
            struct timespec delay = {0, 1000000};
            nanosleep(&delay, NULL);
            s = dt_cancel(x, &e);
            check("bulk_cancel_request", s == DT_OK, s, e.system_errno, 0);
            s = dt_reap(d, 1500, &done, &e);
            if (s)
                goto fatal;
            const dt_completion *r = dt_transfer_result(done);
            check("bulk_cancel_result", r->status == DT_ERROR_CANCELLED, r->status,
                  r->kernel_status, r->actual_length);
            (void)dt_transfer_free(done, NULL);
        }
        for (unsigned i = 0; i < 5; i++) {
            s = dt_submit_endpoint(d, 0, DT_TRANSFER_BULK, 0x82, NULL, 64, 10, NULL, &x, &e);
            if (s)
                goto fatal;
            s = dt_reap(d, 500, &done, &e);
            if (s)
                goto fatal;
            const dt_completion *r = dt_transfer_result(done);
            check("bulk_deadline", r->status == DT_ERROR_TIMEOUT, r->status, r->kernel_status,
                  r->actual_length);
            (void)dt_transfer_free(done, NULL);
        }
        s = dt_release_interface(d, 0, &e);
        check("release_reattach", s == DT_OK, s, e.system_errno, 0);
        if (s)
            goto fatal;
    }
    if (reset) {
        s = dt_reset(d, &e);
        check("device_reset", s == DT_OK, s, e.system_errno, 0);
        if (!s) {
            s = dt_get_descriptor(d, 1, 0, 0, b, 18, &actual, &e);
            check("post_reset_descriptor", s == DT_OK && actual == 18, s, e.system_errno, actual);
        }
    }
    /* Close with work still unreaped, then reopen repeatedly. */
    for (unsigned i = 0; i < 20; i++) {
        s = dt_submit_control(d, &setup, NULL, 1000, NULL, &x, &e);
        if (s)
            goto fatal;
        dt_close(d);
        d = NULL;
        s = dt_open(c, info, &d, &e);
        check("close_pending_reopen", s == DT_OK, s, e.system_errno, 0);
        if (s)
            goto fatal;
    }
    if (endpoint) {
        s = dt_claim_interface(d, 0, 1, &e);
        if (s)
            goto fatal;
        s = dt_submit_endpoint(d, 0, DT_TRANSFER_BULK, 0x82, NULL, 64, 0, NULL, &x, &e);
        if (s)
            goto fatal;
        if (hold) {
            signal(SIGTERM, signal_stop);
            signal(SIGINT, signal_stop);
            puts("{\"test\":\"signal_ready\",\"pass\":true}");
            fflush(stdout);
            /* Maximum 5s even if the harness fails to signal. */
            for (unsigned i = 0; i < 500 && !stop_requested; i++) {
                s = dt_reap(d, 10, &done, &e);
                if (s == DT_OK)
                    break;
            }
            check("signal_cleanup", stop_requested, DT_OK, 0, 0);
        }
        dt_close(d);
        d = NULL;
        s = dt_open(c, info, &d, &e);
        check("close_pending_bulk", s == DT_OK, s, e.system_errno, 0);
        if (s)
            goto fatal;
        s = dt_get_descriptor(d, 1, 0, 0, b, 18, &actual, &e);
        check("after_bulk_close", s == DT_OK && actual == 18, s, e.system_errno, actual);
    }
    dt_close(d);
    d = NULL;
    dt_device_list_free(list);
    list = NULL;
    dt_context_destroy(c);
    c = NULL;
    int after = fd_count();
    check("fd_cleanup", before == after && before >= 0, DT_OK, 0, (size_t)(after - before));
    puts("{\"test\":\"physical_disconnect_reconnect\",\"skipped\":true,"
         "\"reason\":\"requires physical cable operation\"}");
    printf("{\"summary\":true,\"checks\":%u,\"failures\":%u}\n", checks, failures);
    return failures ? 1 : 0;
fatal:
    fprintf(stderr, "fatal: %s %s (%s)\n", e.operation, e.message, dt_status_name(s));
    dt_device_list_free(list);
    dt_context_destroy(c);
    return 1;
}
