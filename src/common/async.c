// SPDX-License-Identifier: MIT
#include "internal.h"
#include <errno.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>
uint64_t dt_now_ns(const dt_context *c) { return c ? c->ops->now(c) : 0; }
uint8_t *dt_xfer_buffer(dt_transfer *x) {
    return x->wire + (x->type == DT_TRANSFER_CONTROL ? 8 : 0);
}
void dt_transfer_cleanup(dt_device *d) {
    dt_transfer *x = d->transfers;
    while (x) {
        dt_transfer *next = x->next;
        free(x->backend);
        free(x->wire);
        free(x);
        x = next;
    }
}
static dt_status submit(dt_transfer *x, const void *data, uint32_t ms, void *user,
                        dt_transfer **out, dt_error *e) {
    dt_device *d = x->dev;
    size_t before = x->type == DT_TRANSFER_CONTROL ? 8 : 0;
    int in = x->type == DT_TRANSFER_CONTROL ? x->setup.request_type & 0x80 : x->endpoint & 0x80;
    dt_status s;
    if (d->allocated >= 64) {
        free(x);
        return dt_fail(e, DT_ERROR_BUSY, 0, "submit",
                       "64 allocated transfers; reap and free first");
    }
    x->wire = calloc(1, before + x->length + 1);
    if (!x->wire) {
        free(x);
        return dt_sysfail(e, "submit", ENOMEM);
    }
    if (!in && x->length)
        memcpy(dt_xfer_buffer(x), data, x->length);
    if (before) {
        x->wire[0] = x->setup.request_type;
        x->wire[1] = x->setup.request;
        x->wire[2] = (uint8_t)x->setup.value;
        x->wire[3] = (uint8_t)(x->setup.value >> 8);
        x->wire[4] = (uint8_t)x->setup.index;
        x->wire[5] = (uint8_t)(x->setup.index >> 8);
        x->wire[6] = (uint8_t)x->setup.length;
        x->wire[7] = (uint8_t)(x->setup.length >> 8);
    }
    x->result.submitted_ns = dt_now_ns(d->ctx);
    x->result.user = user;
    x->deadline = ms ? x->result.submitted_ns + (uint64_t)ms * 1000000 : UINT64_MAX;
    s = d->ctx->ops->submit(x, e);
    if (s) {
        free(x->backend);
        free(x->wire);
        free(x);
        return s;
    }
    x->next = d->transfers;
    d->transfers = x;
    d->pending++;
    d->allocated++;
    *out = x;
    return DT_OK;
}
dt_status dt_submit_control(dt_device *d, const dt_setup *s, const void *data, uint32_t ms,
                            void *user, dt_transfer **out, dt_error *e) {
    dt_transfer *x;
    dt_error_clear(e);
    if (out)
        *out = NULL;
    if (!d || !s || !out || s->length > DT_MAX_CONTROL_LENGTH ||
        (!(s->request_type & 0x80) && s->length && !data))
        return dt_fail(e, DT_ERROR_INVALID, 0, "submit", "invalid control request");
    x = calloc(1, sizeof(*x));
    if (!x)
        return dt_sysfail(e, "submit", ENOMEM);
    x->dev = d;
    x->setup = *s;
    x->length = s->length;
    return submit(x, data, ms, user, out, e);
}
dt_status dt_submit_endpoint(dt_device *d, unsigned i, dt_transfer_type type, uint8_t ep,
                             const void *data, uint32_t len, uint32_t ms, void *user,
                             dt_transfer **out, dt_error *e) {
    dt_transfer *x;
    dt_error_clear(e);
    if (out)
        *out = NULL;
    if (!d || !out || i > 255 || !d->claimed[i] ||
        (type != DT_TRANSFER_BULK && type != DT_TRANSFER_INTERRUPT) || !(ep & 15) || (ep & 0x70) ||
        len > DT_MAX_ENDPOINT_LENGTH || (!(ep & 0x80) && len && !data))
        return dt_fail(e, DT_ERROR_INVALID, 0, "submit",
                       "invalid endpoint, length or unclaimed interface");
    x = calloc(1, sizeof(*x));
    if (!x)
        return dt_sysfail(e, "submit", ENOMEM);
    x->dev = d;
    x->type = type;
    x->endpoint = ep;
    x->length = len;
    x->interface_number = i;
    return submit(x, data, ms, user, out, e);
}
dt_status dt_cancel(dt_transfer *x, dt_error *e) {
    dt_status s;
    dt_error_clear(e);
    if (!x)
        return dt_fail(e, DT_ERROR_INVALID, 0, "cancel", "null transfer");
    if (x->reaped)
        return dt_fail(e, DT_ERROR_NOT_PENDING, 0, "cancel", "already reaped");
    s = x->dev->ctx->ops->cancel(x, e);
    if (!s) {
        x->result.cancelled_ns = dt_now_ns(x->dev->ctx);
        x->deadline = UINT64_MAX;
    }
    return s;
}
static dt_status finish(dt_transfer *x, dt_transfer **out, dt_error *e) {
    if (x->timeout_requested && x->result.status == DT_ERROR_CANCELLED)
        x->result.status = DT_ERROR_TIMEOUT;
    x->reaped = true;
    x->dev->pending--;
    x->result.reaped_ns = dt_now_ns(x->dev->ctx);
    free(x->backend);
    x->backend = NULL;
    *out = x;
    dt_error_clear(e);
    return DT_OK;
}
dt_status dt_reap(dt_device *d, int wait_ms, dt_transfer **out, dt_error *e) {
    uint64_t end;
    dt_status s;
    dt_error_clear(e);
    if (out)
        *out = NULL;
    if (!d || !out || wait_ms < -1)
        return dt_fail(e, DT_ERROR_INVALID, 0, "reap", "bad argument");
    end = wait_ms < 0 ? UINT64_MAX : dt_now_ns(d->ctx) + (uint64_t)wait_ms * 1000000;
    while (d->pending) {
        dt_transfer *x = NULL;
        uint64_t now, wake = end;
        bool acted = false;
        /* Reap queued completions before enforcing user-space deadlines. */
        s = d->ctx->ops->poll(d, &x, e);
        if (s == DT_OK)
            return finish(x, out, e);
        if (s != DT_ERROR_AGAIN)
            return s;
        now = dt_now_ns(d->ctx);
        for (x = d->transfers; x; x = x->next) {
            if (x->reaped)
                continue;
            if (x->deadline <= now && x->deadline != UINT64_MAX) {
                s = dt_cancel(x, e);
                if (s == DT_OK)
                    x->timeout_requested = true;
                else if (s != DT_ERROR_NOT_PENDING && s != DT_ERROR_NO_DEVICE)
                    return s;
                x->deadline = UINT64_MAX;
                /* Poll again after cancellation, including wait_ms=0. */
                acted = true;
            }
            if (x->deadline < wake)
                wake = x->deadline;
        }
        if (acted)
            continue;
        if (now >= end)
            break;
        int ms = wake == UINT64_MAX ? -1
                                    : (int)((wake - now + 999999) / 1000000 > INT_MAX
                                                ? INT_MAX
                                                : (wake - now + 999999) / 1000000);
        s = d->ctx->ops->wait(d, ms, e);
        if (s != DT_OK)
            return s;
    }
    return dt_fail(e, DT_ERROR_AGAIN, 0, "reap", "no completed transfer within wait budget");
}
const dt_completion *dt_transfer_result(const dt_transfer *x) {
    return x && x->reaped ? &x->result : NULL;
}
const uint8_t *dt_transfer_data(const dt_transfer *x) {
    return x && x->reaped ? x->wire + (x->type == DT_TRANSFER_CONTROL ? 8 : 0) : NULL;
}
dt_status dt_transfer_free(dt_transfer *x, dt_error *e) {
    dt_transfer **p;
    dt_error_clear(e);
    if (!x)
        return DT_OK;
    if (!x->reaped)
        return dt_fail(e, DT_ERROR_BUSY, 0, "transfer_free", "reap before freeing");
    for (p = &x->dev->transfers; *p && *p != x; p = &(*p)->next) {
    }
    if (*p)
        *p = x->next;
    x->dev->allocated--;
    free(x->wire);
    free(x);
    return DT_OK;
}
