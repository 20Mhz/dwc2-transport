// SPDX-License-Identifier: MIT
/* Error mapping and dispatch adapted from DWC2 HostLab 6df8d90 (MIT). */
#include "internal.h"
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
uint32_t dt_api_version(void) { return (DT_API_MAJOR << 16) | DT_API_MINOR; }
const char *dt_version(void) { return DT_VERSION; }
void dt_error_clear(dt_error *e) {
    if (e)
        memset(e, 0, sizeof(*e));
}
dt_status dt_fail(dt_error *e, dt_status s, int n, const char *op, const char *fmt, ...) {
    if (e) {
        va_list ap;
        memset(e, 0, sizeof(*e));
        e->status = s;
        e->system_errno = n;
        snprintf(e->operation, sizeof(e->operation), "%s", op);
        va_start(ap, fmt);
        vsnprintf(e->message, sizeof(e->message), fmt, ap);
        va_end(ap);
    }
    return s;
}
const char *dt_status_name(dt_status s) {
    switch (s) {
#define S(x, n)                                                                                    \
    case x:                                                                                        \
        return n
        S(DT_OK, "ok");
        S(DT_ERROR_INVALID, "invalid");
        S(DT_ERROR_NO_DEVICE, "no_device");
        S(DT_ERROR_ACCESS, "access");
        S(DT_ERROR_BUSY, "busy");
        S(DT_ERROR_TIMEOUT, "timeout");
        S(DT_ERROR_STALL, "stall");
        S(DT_ERROR_PROTOCOL, "protocol");
        S(DT_ERROR_OVERFLOW, "overflow");
        S(DT_ERROR_CANCELLED, "cancelled");
        S(DT_ERROR_NOT_PENDING, "not_pending");
        S(DT_ERROR_IO, "io");
        S(DT_ERROR_NOMEM, "nomem");
        S(DT_ERROR_UNSUPPORTED, "unsupported");
        S(DT_ERROR_AGAIN, "again");
#undef S
    }
    return "unknown";
}
const char *dt_speed_name(dt_speed s) {
    switch (s) {
    case DT_SPEED_LOW:
        return "low";
    case DT_SPEED_FULL:
        return "full";
    case DT_SPEED_HIGH:
        return "high";
    case DT_SPEED_SUPER:
        return "super";
    case DT_SPEED_SUPER_PLUS:
        return "super_plus";
    case DT_SPEED_WIRELESS:
        return "wireless";
    default:
        return "unknown";
    }
}
dt_status dt_errno_status(int e) {
    if (e < 0)
        e = -e;
    switch (e) {
    case 0:
        return DT_OK;
    case ENOENT:
    case ENODEV:
    case ESHUTDOWN:
        return DT_ERROR_NO_DEVICE;
    case EINVAL:
        return DT_ERROR_INVALID;
    case EACCES:
    case EPERM:
        return DT_ERROR_ACCESS;
    case EBUSY:
        return DT_ERROR_BUSY;
    case ETIMEDOUT:
        return DT_ERROR_TIMEOUT;
    case EPIPE:
        return DT_ERROR_STALL;
    case EPROTO:
    case EILSEQ:
        return DT_ERROR_PROTOCOL;
    case EOVERFLOW:
        return DT_ERROR_OVERFLOW;
    case ECONNRESET:
        return DT_ERROR_CANCELLED;
    case ENOMEM:
        return DT_ERROR_NOMEM;
    case EAGAIN:
        return DT_ERROR_AGAIN;
    case ENOTTY:
    case ENOSYS:
        return DT_ERROR_UNSUPPORTED;
    default:
        return DT_ERROR_IO;
    }
}
dt_status dt_sysfail(dt_error *e, const char *op, int n) {
    return dt_fail(e, dt_errno_status(n), n, op, "%s", strerror(n));
}
dt_status dt_context_create(const char *name, dt_context **out, dt_error *e) {
    dt_context *c;
    dt_error_clear(e);
    if (out)
        *out = NULL;
    if (!out || !name)
        return dt_fail(e, DT_ERROR_INVALID, 0, "context_create", "bad argument");
    c = calloc(1, sizeof(*c));
    if (!c)
        return dt_sysfail(e, "context_create", ENOMEM);
    if (!strcmp(name, "mock"))
        c->ops = &dt_mock_ops;
#ifdef __linux__
    if (!strcmp(name, "linux-usbfs"))
        c->ops = &dt_linux_ops;
#endif
    if (!c->ops) {
        free(c);
        return dt_fail(e, DT_ERROR_UNSUPPORTED, 0, "context_create", "backend unavailable");
    }
    if (c->ops == &dt_mock_ops && dt_mock_init(c, e) != DT_OK) {
        free(c);
        return e ? e->status : DT_ERROR_NOMEM;
    }
    *out = c;
    return DT_OK;
}
void dt_context_destroy(dt_context *c) {
    if (!c)
        return;
    while (c->devices)
        dt_close(c->devices);
    if (c->ops == &dt_mock_ops)
        dt_mock_fini(c);
    free(c);
}
const char *dt_backend_name(const dt_context *c) { return c ? c->ops->name : "unavailable"; }
dt_status dt_enumerate(dt_context *c, dt_device_info **out, size_t *n, dt_error *e) {
    dt_error_clear(e);
    if (out)
        *out = NULL;
    if (n)
        *n = 0;
    if (!c || !out || !n)
        return dt_fail(e, DT_ERROR_INVALID, 0, "enumerate", "bad argument");
    return c->ops->enumerate(c, out, n, e);
}
void dt_device_list_free(dt_device_info *p) { free(p); }
dt_status dt_open(dt_context *c, const dt_device_info *info, dt_device **out, dt_error *e) {
    dt_device *d;
    dt_status s;
    dt_error_clear(e);
    if (out)
        *out = NULL;
    if (!c || !info || !out || !memchr(info->path, 0, sizeof(info->path)))
        return dt_fail(e, DT_ERROR_INVALID, 0, "open", "bad argument");
    d = calloc(1, sizeof(*d));
    if (!d)
        return dt_sysfail(e, "open", ENOMEM);
    d->ctx = c;
    d->info = *info;
    d->fd = -1;
    s = c->ops->open(d, e);
    if (s) {
        free(d);
        return s;
    }
    d->next = c->devices;
    c->devices = d;
    *out = d;
    return DT_OK;
}
void dt_close(dt_device *d) {
    dt_device **p;
    if (!d)
        return;
    d->ctx->ops->close(d);
    for (p = &d->ctx->devices; *p && *p != d; p = &(*p)->next) {
    }
    if (*p)
        *p = d->next;
    dt_transfer_cleanup(d);
    free(d);
}
const dt_device_info *dt_device_get_info(const dt_device *d) { return d ? &d->info : NULL; }
uint32_t dt_capabilities(const dt_device *d) {
    return d ? DT_CAP_CONTROL | DT_CAP_RESET | DT_CAP_CLAIM | DT_CAP_ASYNC_CONTROL | DT_CAP_CANCEL |
                   DT_CAP_ASYNC_ENDPOINT | (d->ctx->ops == &dt_mock_ops ? DT_CAP_VIRTUAL_CLOCK : 0)
             : 0;
}
dt_status dt_control(dt_device *d, const dt_setup *s, void *b, uint32_t ms, size_t *n,
                     dt_error *e) {
    dt_error_clear(e);
    if (n)
        *n = 0;
    if (!d || !s || !n || (s->length && !b) || s->length > DT_MAX_CONTROL_LENGTH)
        return dt_fail(e, DT_ERROR_INVALID, 0, "control", "invalid buffer or control length");
    return d->ctx->ops->control(d, s, b, ms, n, e);
}
dt_status dt_get_descriptor(dt_device *d, uint8_t t, uint8_t i, uint16_t lang, void *b,
                            uint16_t len, size_t *n, dt_error *e) {
    dt_setup s = {0x80, 6, (uint16_t)((t << 8) | i), lang, len};
    return dt_control(d, &s, b, 1000, n, e);
}
dt_status dt_claim_interface(dt_device *d, unsigned i, int detach, dt_error *e) {
    dt_status s;
    dt_error_clear(e);
    if (!d || i > 255 || (detach != 0 && detach != 1))
        return dt_fail(e, DT_ERROR_INVALID, 0, "claim", "bad argument");
    if (d->claimed[i])
        return dt_fail(e, DT_ERROR_BUSY, 0, "claim", "already claimed");
    s = d->ctx->ops->claim(d, i, detach, e);
    if (!s)
        d->claimed[i] = true;
    return s;
}
dt_status dt_release_interface(dt_device *d, unsigned i, dt_error *e) {
    dt_status s;
    dt_error_clear(e);
    if (!d || i > 255 || !d->claimed[i])
        return dt_fail(e, DT_ERROR_INVALID, 0, "release", "interface not claimed");
    for (dt_transfer *x = d->transfers; x; x = x->next)
        if (!x->reaped && x->type != DT_TRANSFER_CONTROL && x->interface_number == i)
            return dt_fail(e, DT_ERROR_BUSY, 0, "release", "reap endpoint transfers first");
    s = d->ctx->ops->release(d, i, d->detached[i], e);
    /* Release may succeed while reattach fails: backend clears the claim. */
    return s;
}
dt_status dt_reset(dt_device *d, dt_error *e) {
    dt_error_clear(e);
    if (!d)
        return dt_fail(e, DT_ERROR_INVALID, 0, "reset", "bad argument");
    if (d->pending)
        return dt_fail(e, DT_ERROR_BUSY, 0, "reset", "reap pending transfers first");
    for (unsigned i = 0; i < 256; i++)
        if (d->claimed[i])
            return dt_fail(e, DT_ERROR_BUSY, 0, "reset", "release interfaces first");
    return d->ctx->ops->reset(d, e);
}
