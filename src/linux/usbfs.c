// SPDX-License-Identifier: MIT
/* Conventional usbfs operations adapted from DWC2 HostLab 6df8d90,
 * src/lib/backend_linux.c, Copyright (c) 2026 Ronald Valenzuela (MIT). */
#ifdef __linux__
#include "../common/internal.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/usbdevice_fs.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#define SYSFS_USB "/sys/bus/usb/devices"
static int read_attr(const char *dev, const char *attr, char *buf, size_t len) {
    char path[512];
    FILE *f;
    size_t n;
    snprintf(path, sizeof(path), SYSFS_USB "/%s/%s", dev, attr);
    f = fopen(path, "re");
    if (!f)
        return -1;
    n = fread(buf, 1, len - 1, f);
    fclose(f);
    buf[n] = 0;
    while (n && (buf[n - 1] == '\n' || buf[n - 1] == ' '))
        buf[--n] = 0;
    return n ? 0 : -1;
}
static long read_num(const char *dev, const char *attr, int base) {
    char buf[64], *end;
    long n;
    if (read_attr(dev, attr, buf, sizeof(buf)))
        return -1;
    errno = 0;
    n = strtol(buf, &end, base);
    return errno || *end ? -1 : n;
}
static void link_name(const char *path, char *out, size_t cap) {
    char b[512];
    ssize_t n = readlink(path, b, sizeof(b) - 1);
    const char *p;
    if (n < 0)
        return;
    b[n] = 0;
    p = strrchr(b, '/');
    snprintf(out, cap, "%.*s", (int)cap - 1, p ? p + 1 : b);
}
static void drivers(const char *name, dt_device_info *info) {
    DIR *dir = opendir(SYSFS_USB);
    struct dirent *de;
    char p[512], b[128];
    size_t used = 0;
    if (!dir)
        return;
    while ((de = readdir(dir))) {
        size_t len = strlen(name);
        if (strncmp(de->d_name, name, len) || de->d_name[len] != ':')
            continue;
        snprintf(p, sizeof(p), SYSFS_USB "/%s/driver", de->d_name);
        b[0] = 0;
        link_name(p, b, sizeof(b));
        if (b[0] && used + strlen(b) + 2 < sizeof(info->driver)) {
            if (used)
                info->driver[used++] = ',';
            memcpy(info->driver + used, b, strlen(b) + 1);
            used += strlen(b);
        }
    }
    closedir(dir);
}
static int fill_info(const char *name, dt_device_info *info) {
    char b[64], path[512];
    long bus = read_num(name, "busnum", 10), dev = read_num(name, "devnum", 10);
    long vid = read_num(name, "idVendor", 16), pid = read_num(name, "idProduct", 16),
         cls = read_num(name, "bDeviceClass", 16);
    if (bus < 1 || bus > 255 || dev < 1 || dev > 127 || vid < 0 || vid > 65535 || pid < 0 ||
        pid > 65535 || cls < 0 || cls > 255)
        return -1;
    memset(info, 0, sizeof(*info));
    info->bus = (uint8_t)bus;
    info->address = (uint8_t)dev;
    info->vendor_id = (uint16_t)vid;
    info->product_id = (uint16_t)pid;
    info->device_class = (uint8_t)cls;
    if (!read_attr(name, "speed", b, sizeof(b))) {
        if (!strcmp(b, "1.5"))
            info->speed = DT_SPEED_LOW;
        else if (!strcmp(b, "12"))
            info->speed = DT_SPEED_FULL;
        else if (!strcmp(b, "480"))
            info->speed = DT_SPEED_HIGH;
        else if (!strcmp(b, "5000"))
            info->speed = DT_SPEED_SUPER;
        else if (!strcmp(b, "10000") || !strcmp(b, "20000"))
            info->speed = DT_SPEED_SUPER_PLUS;
    }
    if (!read_attr(name, "devpath", b, sizeof(b)) && strcmp(b, "0")) {
        char *p = b, *end;
        while (*p && info->port_count < sizeof(info->ports)) {
            unsigned long n = strtoul(p, &end, 10);
            if (end == p || n > 255)
                break;
            info->ports[info->port_count++] = (uint8_t)n;
            p = end;
            if (*p == '.')
                p++;
        }
    }
    snprintf(info->path, sizeof(info->path), "/dev/bus/usb/%03ld/%03ld", bus, dev);
    snprintf(info->sysfs_name, sizeof(info->sysfs_name), "%.63s", name);
    drivers(name, info);
    snprintf(path, sizeof(path), SYSFS_USB "/usb%ld/../driver", bus);
    link_name(path, info->controller, sizeof(info->controller));
    return 0;
}
static int info_cmp(const void *a, const void *b) {
    const dt_device_info *x = a, *y = b;
    return x->bus != y->bus ? (int)x->bus - y->bus : (int)x->address - y->address;
}
static dt_status lx_enumerate(dt_context *c, dt_device_info **out, size_t *count, dt_error *e) {
    DIR *dir = opendir(SYSFS_USB);
    struct dirent *de;
    dt_device_info *list = NULL;
    size_t n = 0;
    (void)c;
    if (!dir)
        return dt_sysfail(e, "enumerate", errno);
    while ((de = readdir(dir))) {
        dt_device_info info, *p;
        if (de->d_name[0] == '.' || strchr(de->d_name, ':') || fill_info(de->d_name, &info))
            continue;
        p = realloc(list, (n + 1) * sizeof(*p));
        if (!p) {
            free(list);
            closedir(dir);
            return dt_sysfail(e, "enumerate", ENOMEM);
        }
        list = p;
        list[n++] = info;
    }
    closedir(dir);
    if (n > 1)
        qsort(list, n, sizeof(*list), info_cmp);
    *out = list;
    *count = n;
    return DT_OK;
}
static dt_status lx_open(dt_device *d, dt_error *e) {
    char expected[128];
    struct stat st;
    uint8_t desc[18];
    ssize_t n;
    snprintf(expected, sizeof(expected), "/dev/bus/usb/%03u/%03u", d->info.bus, d->info.address);
    if (!d->info.bus || !d->info.address || d->info.address > 127 || strcmp(expected, d->info.path))
        return dt_fail(e, DT_ERROR_INVALID, 0, "open", "use an exact enumerated usbfs path");
    d->fd = open(expected, O_RDWR | O_CLOEXEC | O_NOFOLLOW);
    if (d->fd < 0)
        return dt_sysfail(e, "open", errno);
    if (fstat(d->fd, &st) || !S_ISCHR(st.st_mode)) {
        close(d->fd);
        d->fd = -1;
        return dt_fail(e, DT_ERROR_INVALID, 0, "open", "not a usbfs device");
    }
    n = pread(d->fd, desc, sizeof(desc), 0);
    if (n != 18 || desc[1] != 1 ||
        ((unsigned)desc[8] | ((unsigned)desc[9] << 8)) != d->info.vendor_id ||
        ((unsigned)desc[10] | ((unsigned)desc[11] << 8)) != d->info.product_id) {
        close(d->fd);
        d->fd = -1;
        return dt_fail(e, DT_ERROR_NO_DEVICE, 0, "open",
                       "device disappeared or discovery identity changed");
    }
    return DT_OK;
}
static dt_status lx_release(dt_device *d, unsigned i, int restore, dt_error *e) {
    unsigned int intf = i;
    if (ioctl(d->fd, USBDEVFS_RELEASEINTERFACE, &intf))
        return dt_sysfail(e, "release", errno);
    d->claimed[i] = false;
    if (restore) {
        struct usbdevfs_ioctl ic = {.ifno = (int)i, .ioctl_code = USBDEVFS_CONNECT};
        if (ioctl(d->fd, USBDEVFS_IOCTL, &ic) < 0)
            return dt_sysfail(e, "reattach", errno);
    }
    d->detached[i] = false;
    return DT_OK;
}
static void lx_close(dt_device *d) {
    for (dt_transfer *x = d->transfers; x; x = x->next)
        if (!x->reaped && x->backend)
            (void)ioctl(d->fd, USBDEVFS_DISCARDURB, x->backend);
    for (unsigned i = 0; i < 256; i++) {
        if (d->claimed[i]) {
            (void)lx_release(d, i, d->detached[i], NULL);
        } else if (d->detached[i]) {
            struct usbdevfs_ioctl ic = {.ifno = (int)i, .ioctl_code = USBDEVFS_CONNECT};
            (void)ioctl(d->fd, USBDEVFS_IOCTL, &ic);
        }
    }
    close(d->fd);
}
static dt_status lx_control(dt_device *d, const dt_setup *s, void *data, uint32_t ms,
                            size_t *actual, dt_error *e) {
    struct usbdevfs_ctrltransfer ct = {.bRequestType = s->request_type,
                                       .bRequest = s->request,
                                       .wValue = s->value,
                                       .wIndex = s->index,
                                       .wLength = s->length,
                                       .timeout = ms,
                                       .data = data};
    if (d->fd < 0)
        return dt_fail(e, DT_ERROR_NO_DEVICE, 0, "control", "device disconnected");
    int n = ioctl(d->fd, USBDEVFS_CONTROL, &ct);
    if (n < 0)
        return dt_sysfail(e, "control", errno);
    *actual = (size_t)n;
    return DT_OK;
}
static dt_status lx_claim(dt_device *d, unsigned i, int detach, dt_error *e) {
    unsigned int intf = i;
    if (d->fd < 0)
        return dt_fail(e, DT_ERROR_NO_DEVICE, 0, "claim", "device disconnected");
    if (detach) {
        struct usbdevfs_getdriver gd = {.interface = i};
        struct usbdevfs_disconnect_claim dc = {.interface = i};
        int bound = ioctl(d->fd, USBDEVFS_GETDRIVER, &gd) == 0;
        if (ioctl(d->fd, USBDEVFS_DISCONNECT_CLAIM, &dc))
            return dt_sysfail(e, "claim_detach", errno);
        d->detached[i] = bound;
    } else if (ioctl(d->fd, USBDEVFS_CLAIMINTERFACE, &intf))
        return dt_sysfail(e, "claim", errno);
    return DT_OK;
}
static dt_status lx_reset(dt_device *d, dt_error *e) {
    if (d->fd < 0)
        return dt_fail(e, DT_ERROR_NO_DEVICE, 0, "reset", "device disconnected");
    return ioctl(d->fd, USBDEVFS_RESET, 0) ? dt_sysfail(e, "reset", errno) : DT_OK;
}
/* URB submission/cancel/reap mapping from HostLab; buffers and URBs are
 * tracked by the owning device and retained until kernel work is stopped. */
static uint64_t lx_now(const dt_context *c) {
    struct timespec t;
    (void)c;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec * 1000000000 + (uint64_t)t.tv_nsec;
}
static dt_status lx_submit(dt_transfer *x, dt_error *e) {
    if (x->dev->fd < 0)
        return dt_fail(e, DT_ERROR_NO_DEVICE, 0, "submit", "device disconnected");
    struct usbdevfs_urb *u = calloc(1, sizeof(*u));
    if (!u)
        return dt_sysfail(e, "submit", ENOMEM);
    x->backend = u;
    u->type = x->type == DT_TRANSFER_CONTROL ? USBDEVFS_URB_TYPE_CONTROL
              : x->type == DT_TRANSFER_BULK  ? USBDEVFS_URB_TYPE_BULK
                                             : USBDEVFS_URB_TYPE_INTERRUPT;
    u->endpoint = x->endpoint;
    u->buffer = x->wire;
    u->buffer_length = (int)x->length + (x->type == DT_TRANSFER_CONTROL ? 8 : 0);
    u->usercontext = x;
    return ioctl(x->dev->fd, USBDEVFS_SUBMITURB, u) ? dt_sysfail(e, "submit", errno) : DT_OK;
}
static dt_status lx_cancel(dt_transfer *x, dt_error *e) {
    if (x->ready)
        return dt_fail(e, DT_ERROR_NOT_PENDING, 0, "cancel", "already completed");
    if (ioctl(x->dev->fd, USBDEVFS_DISCARDURB, x->backend)) {
        int n = errno;
        if (n == EINVAL)
            return dt_fail(e, DT_ERROR_NOT_PENDING, n, "cancel", "completion already queued");
        return dt_sysfail(e, "cancel", n);
    }
    return DT_OK;
}
static dt_status lx_poll(dt_device *d, dt_transfer **out, dt_error *e) {
    struct usbdevfs_urb *u = NULL;
    dt_transfer *x;
    for (x = d->transfers; x; x = x->next)
        if (x->ready && !x->reaped) {
            *out = x;
            return DT_OK;
        }
    if (ioctl(d->fd, USBDEVFS_REAPURBNDELAY, &u)) {
        int n = errno;
        if (n == ENODEV || n == ESHUTDOWN) {
            /* Closing usbfs synchronously kills pending kernel work before
             * any user-owned allocation is released. Drain synthetic results. */
            close(d->fd);
            d->fd = -1;
            for (x = d->transfers; x; x = x->next)
                if (!x->reaped) {
                    free(x->backend);
                    x->backend = NULL;
                    x->ready = true;
                    x->result.status = DT_ERROR_NO_DEVICE;
                    x->result.kernel_status = -n;
                    x->result.actual_length = 0;
                }
            for (x = d->transfers; x; x = x->next)
                if (!x->reaped) {
                    *out = x;
                    return DT_OK;
                }
        }
        return dt_sysfail(e, "reap", n);
    }
    x = u->usercontext;
    x->ready = true;
    x->result.kernel_status = u->status;
    x->result.status = u->status == -ENOENT ? DT_ERROR_CANCELLED : dt_errno_status(u->status);
    if (u->actual_length < 0 || (uint32_t)u->actual_length > x->length) {
        x->result.status = DT_ERROR_OVERFLOW;
        x->result.actual_length = 0;
    } else
        x->result.actual_length = (size_t)u->actual_length;
    *out = x;
    return DT_OK;
}
static dt_status lx_wait(dt_device *d, int ms, dt_error *e) {
    struct pollfd p = {.fd = d->fd, .events = POLLOUT};
    int n = poll(&p, 1, ms);
    /* The common absolute deadline survives EINTR, spurious readiness and HUP. */
    return n < 0 && errno != EINTR ? dt_sysfail(e, "poll", errno) : DT_OK;
}
const struct dt_ops dt_linux_ops = {"linux-usbfs", lx_enumerate, lx_open,  lx_close,  lx_control,
                                    lx_claim,      lx_release,   lx_reset, lx_submit, lx_cancel,
                                    lx_poll,       lx_wait,      lx_now};
#endif
