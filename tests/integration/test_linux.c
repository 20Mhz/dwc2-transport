// SPDX-License-Identifier: MIT
/* Exercise actual Linux backend logic with simulated usbfs syscall outcomes.
 * Complements (does not replace) recorded physical-controller regression. */
#include "../../src/common/internal.h"
#include <errno.h>
#include <linux/usbdevice_fs.h>
#include <poll.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>
static struct usbdevfs_urb *urbs[8];
static unsigned pending, closed, calls, interrupts;
static int disconnected, ready;
static uint64_t fake_ns;
static unsigned checks;
#define C(x)                                                                                       \
    do {                                                                                           \
        checks++;                                                                                  \
        if (!(x)) {                                                                                \
            fprintf(stderr, "line %d: %s\n", __LINE__, #x);                                        \
            exit(1);                                                                               \
        }                                                                                          \
    } while (0)
int __wrap_ioctl(int fd, unsigned long request, ...);
int __wrap_poll(struct pollfd *, nfds_t, int);
int __wrap_clock_gettime(clockid_t, struct timespec *);
int __wrap_close(int);
int __wrap_ioctl(int fd, unsigned long request, ...) {
    va_list ap;
    void *arg;
    (void)fd;
    va_start(ap, request);
    arg = va_arg(ap, void *);
    va_end(ap);
    if (request == USBDEVFS_SUBMITURB) {
        C(pending < 8);
        urbs[pending++] = arg;
        return 0;
    }
    if (request == USBDEVFS_DISCARDURB) {
        struct usbdevfs_urb *u = arg;
        u->status = -ENOENT;
        u->actual_length = 0;
        ready = 1;
        return 0;
    }
    if (request == USBDEVFS_REAPURBNDELAY) {
        if (disconnected) {
            errno = ENODEV;
            return -1;
        }
        if (!ready || !pending) {
            errno = EAGAIN;
            return -1;
        }
        *(void **)arg = urbs[--pending];
        if (!pending)
            ready = 0;
        return 0;
    }
    errno = ENOTTY;
    return -1;
}
int __wrap_poll(struct pollfd *fds, nfds_t n, int ms) {
    (void)fds;
    (void)n;
    calls++;
    if (interrupts) {
        fake_ns += 1000000;
        interrupts--;
        errno = EINTR;
        return -1;
    }
    C(ms >= 0);
    fake_ns += (uint64_t)ms * 1000000;
    return 0;
}
int __wrap_clock_gettime(clockid_t c, struct timespec *t) {
    (void)c;
    t->tv_sec = (time_t)(fake_ns / 1000000000);
    t->tv_nsec = (long)(fake_ns % 1000000000);
    return 0;
}
int __wrap_close(int fd) {
    if (fd >= 0)
        closed++;
    return 0;
}
int main(void) {
    dt_context ctx = {.ops = &dt_linux_ops};
    dt_device *d = calloc(1, sizeof(*d));
    dt_transfer *x, *y, *done;
    dt_setup setup = {0x80, 6, 0x100, 0, 18};
    dt_error e;
    d->ctx = &ctx;
    d->fd = 42;
    ctx.devices = d;
    C(dt_submit_control(d, &setup, NULL, 0, NULL, &x, &e) == DT_OK);
    interrupts = 100;
    C(dt_reap(d, 5, &done, &e) == DT_ERROR_AGAIN);
    C(fake_ns == 5000000 && calls == 5);
    /* Repeated EINTR cannot restart an expired deadline. */
    interrupts = 0;
    C(dt_cancel(x, &e) == DT_OK);
    C(dt_reap(d, 0, &done, &e) == DT_OK);
    C(dt_transfer_result(done)->status == DT_ERROR_CANCELLED);
    C(dt_transfer_free(done, &e) == DT_OK);
    C(dt_submit_control(d, &setup, NULL, 2, NULL, &x, &e) == DT_OK);
    C(dt_reap(d, 5, &done, &e) == DT_OK);
    C(dt_transfer_result(done)->status == DT_ERROR_TIMEOUT);
    C(dt_transfer_free(done, &e) == DT_OK);
    C(dt_submit_control(d, &setup, NULL, 100, NULL, &x, &e) == DT_OK);
    C(dt_submit_control(d, &setup, NULL, 100, NULL, &y, &e) == DT_OK);
    disconnected = 1;
    C(dt_reap(d, 0, &done, &e) == DT_OK);
    C(closed == 1 && d->fd == -1);
    C(dt_transfer_result(done)->status == DT_ERROR_NO_DEVICE);
    C(dt_transfer_free(done, &e) == DT_OK);
    C(dt_reap(d, 0, &done, &e) == DT_OK);
    C(dt_transfer_result(done)->status == DT_ERROR_NO_DEVICE);
    C(dt_transfer_free(done, &e) == DT_OK);
    C(dt_reap(d, 0, &done, &e) == DT_ERROR_AGAIN);
    C(dt_submit_control(d, &setup, NULL, 0, NULL, &x, &e) == DT_ERROR_NO_DEVICE && x == NULL);
    dt_close(d);
    C(ctx.devices == NULL);
    C(closed == 1);
    printf("Linux syscall contracts: %u checks PASS\n", checks);
    return 0;
}
