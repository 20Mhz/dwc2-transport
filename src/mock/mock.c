// SPDX-License-Identifier: MIT
/* Descriptor defaults and virtual-clock/cancellation semantics adapted from
 * HostLab 6df8d90 src/lib/backend_mock.c (MIT). Context-owned state and data.
 */
#include "dwc2_transport/mock.h"
#include "../common/internal.h"
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
struct response {
    dt_setup match;
    int any;
    dt_status status;
    uint8_t *data;
    uint32_t len;
    uint64_t latency;
};
struct mock_state {
    uint64_t now, latency, giveback, generation;
    dt_device_info info;
    dt_device *owner;
    int present;
    struct response queue[128];
    unsigned queued;
};
static const uint8_t device_desc[] = {18,   1, 0, 2, 0xff, 0, 0, 64, 0x09,
                                      0x12, 1, 0, 0, 1,    0, 0, 0,  1};
static const uint8_t config_desc[] = {9, 2, 32, 0, 1,    1, 0,  0x80, 50, 9, 4, 0, 0, 2,  0xff, 0,
                                      0, 0, 7,  5, 0x81, 2, 64, 0,    0,  7, 5, 1, 2, 64, 0,    0};
static dt_status mock_check(dt_context *c, dt_error *e) {
    dt_error_clear(e);
    if (!c || c->ops != &dt_mock_ops)
        return dt_fail(e, DT_ERROR_INVALID, 0, "mock", "mock context required");
    return DT_OK;
}
static int connected(dt_device *d) {
    struct mock_state *s = d->ctx->state;
    return s->present && d->generation == s->generation;
}
dt_status dt_mock_init(dt_context *c, dt_error *e) {
    struct mock_state *s = calloc(1, sizeof(*s));
    if (!s)
        return dt_sysfail(e, "mock_init", ENOMEM);
    s->present = 1;
    s->generation = 1;
    s->latency = 1000000;
    s->info = (dt_device_info){.bus = 1,
                               .address = 2,
                               .vendor_id = 0x1209,
                               .product_id = 1,
                               .device_class = 0xff,
                               .speed = DT_SPEED_HIGH,
                               .port_count = 1,
                               .ports = {1},
                               .path = "mock:1:2",
                               .controller = "mock"};
    c->state = s;
    return DT_OK;
}
void dt_mock_fini(dt_context *c) {
    struct mock_state *s = c->state;
    for (unsigned i = 0; i < s->queued; i++)
        free(s->queue[i].data);
    free(s);
}
dt_status dt_mock_queue_response(dt_context *c, const dt_setup *match, dt_status status,
                                 const void *data, uint32_t len, uint64_t latency, dt_error *e) {
    struct mock_state *s;
    struct response *r;
    if (mock_check(c, e))
        return DT_ERROR_INVALID;
    s = c->state;
    if (s->queued == 128 || len > DT_MAX_ENDPOINT_LENGTH || (len && !data) ||
        latency > UINT64_MAX / 4 || status > DT_OK || status < DT_ERROR_AGAIN)
        return dt_fail(e, DT_ERROR_INVALID, 0, "mock_queue", "invalid response or queue full");
    r = &s->queue[s->queued];
    memset(r, 0, sizeof(*r));
    if (len) {
        r->data = malloc(len);
        if (!r->data)
            return dt_sysfail(e, "mock_queue", ENOMEM);
        memcpy(r->data, data, len);
    }
    r->any = !match;
    if (match)
        r->match = *match;
    r->status = status;
    r->len = len;
    r->latency = latency;
    s->queued++;
    return DT_OK;
}
dt_status dt_mock_set_timing(dt_context *c, uint64_t latency, uint64_t giveback, dt_error *e) {
    struct mock_state *s;
    if (mock_check(c, e))
        return DT_ERROR_INVALID;
    s = c->state;
    if (latency > UINT64_MAX / 4 || giveback > UINT64_MAX / 4)
        return dt_fail(e, DT_ERROR_INVALID, 0, "mock_timing", "timing too large");
    s->latency = latency;
    s->giveback = giveback;
    return DT_OK;
}
dt_status dt_mock_advance(dt_context *c, uint64_t ns, dt_error *e) {
    struct mock_state *s;
    if (mock_check(c, e))
        return DT_ERROR_INVALID;
    s = c->state;
    if (ns > UINT64_MAX / 4 - s->now)
        return dt_fail(e, DT_ERROR_INVALID, 0, "mock_advance", "virtual clock limit");
    s->now += ns;
    return DT_OK;
}
dt_status dt_mock_set_connected(dt_context *c, int present, dt_error *e) {
    struct mock_state *s;
    if (mock_check(c, e))
        return DT_ERROR_INVALID;
    s = c->state;
    if (present != 0 && present != 1)
        return dt_fail(e, DT_ERROR_INVALID, 0, "mock_connect", "expected 0 or 1");
    if (s->present && !present) {
        s->generation++;
        s->owner = NULL;
        for (dt_device *d = c->devices; d; d = d->next) {
            memset(d->claimed, 0, sizeof(d->claimed));
            memset(d->detached, 0, sizeof(d->detached));
            for (dt_transfer *x = d->transfers; x; x = x->next)
                if (!x->reaped && !x->ready && x->mock_done > s->now) {
                    x->ready = true;
                    x->result.status = DT_ERROR_NO_DEVICE;
                    x->result.kernel_status = -ENODEV;
                    x->result.actual_length = 0;
                }
        }
    }
    s->present = present;
    return DT_OK;
}
static dt_status mock_enumerate(dt_context *c, dt_device_info **out, size_t *n, dt_error *e) {
    struct mock_state *s = c->state;
    if (!s->present)
        return DT_OK;
    *out = malloc(sizeof(**out));
    if (!*out)
        return dt_sysfail(e, "enumerate", ENOMEM);
    **out = s->info;
    *n = 1;
    return DT_OK;
}
static dt_status mock_open(dt_device *d, dt_error *e) {
    struct mock_state *s = d->ctx->state;
    if (!s->present || strcmp(d->info.path, s->info.path) ||
        d->info.vendor_id != s->info.vendor_id || d->info.product_id != s->info.product_id)
        return dt_fail(e, DT_ERROR_NO_DEVICE, 0, "open", "mock device absent");
    d->generation = s->generation;
    return DT_OK;
}
static dt_status mock_release(dt_device *d, unsigned i, int restore, dt_error *e) {
    struct mock_state *s = d->ctx->state;
    (void)restore;
    d->claimed[i] = d->detached[i] = false;
    if (s->owner == d)
        s->owner = NULL;
    return connected(d) ? DT_OK : dt_fail(e, DT_ERROR_NO_DEVICE, 0, "release", "disconnected");
}
static void mock_close(dt_device *d) {
    struct mock_state *s = d->ctx->state;
    if (s->owner == d)
        s->owner = NULL;
}
static int same_setup(const dt_setup *a, const dt_setup *b) {
    return a->request_type == b->request_type && a->request == b->request && a->value == b->value &&
           a->index == b->index && a->length == b->length;
}
static void deliver(dt_transfer *x, const uint8_t *p, size_t n, dt_status status) {
    int in = x->type == DT_TRANSFER_CONTROL ? x->setup.request_type & 0x80 : x->endpoint & 0x80;
    x->result.status = status;
    x->result.kernel_status = status == DT_OK ? 0 : status == DT_ERROR_STALL ? -EPIPE : -EIO;
    if (status != DT_OK) {
        x->result.actual_length = 0;
        return;
    }
    if (!in)
        n = x->length;
    if (n > x->length)
        n = x->length;
    if (in && n)
        memcpy(dt_xfer_buffer(x), p, n);
    x->result.actual_length = n;
}
static void resolve(dt_transfer *x, uint64_t *latency) {
    struct mock_state *s = x->dev->ctx->state;
    *latency = s->latency;
    for (unsigned i = 0; i < s->queued; i++) {
        struct response *r = &s->queue[i];
        if (!r->any && (x->type != DT_TRANSFER_CONTROL || !same_setup(&r->match, &x->setup)))
            continue;
        *latency = r->latency;
        deliver(x, r->data, r->len, r->status);
        free(r->data);
        memmove(r, r + 1, (s->queued - i - 1) * sizeof(*r));
        s->queued--;
        return;
    }
    if (x->type != DT_TRANSFER_CONTROL) {
        *latency = UINT64_MAX;
        return;
    }
    if (x->setup.request_type == 0x80 && x->setup.request == 6 && x->setup.value == 0x100)
        deliver(x, device_desc, sizeof(device_desc), DT_OK);
    else if (x->setup.request_type == 0x80 && x->setup.request == 6 && x->setup.value == 0x200)
        deliver(x, config_desc, sizeof(config_desc), DT_OK);
    else if (x->setup.request_type == 0x80 && x->setup.request == 0) {
        static const uint8_t zero[2];
        deliver(x, zero, 2, DT_OK);
    } else
        deliver(x, NULL, 0, DT_ERROR_STALL);
}
static dt_status mock_control(dt_device *d, const dt_setup *req, void *data, uint32_t ms,
                              size_t *actual, dt_error *e) {
    struct mock_state *s = d->ctx->state;
    uint64_t latency;
    dt_transfer x = {.dev = d, .setup = *req, .length = req->length};
    if (!connected(d))
        return dt_fail(e, DT_ERROR_NO_DEVICE, 0, "control", "mock disconnected");
    x.wire = calloc(1, 8u + req->length);
    if (!x.wire)
        return dt_sysfail(e, "control", ENOMEM);
    resolve(&x, &latency);
    if (ms && latency + s->giveback > (uint64_t)ms * 1000000) {
        s->now += (uint64_t)ms * 1000000;
        free(x.wire);
        return dt_fail(e, DT_ERROR_TIMEOUT, 0, "control", "virtual timeout");
    }
    s->now += latency + s->giveback;
    if (x.result.status == DT_OK) {
        *actual = x.result.actual_length;
        if ((req->request_type & 0x80) && *actual)
            memcpy(data, dt_xfer_buffer(&x), *actual);
    }
    free(x.wire);
    return x.result.status == DT_OK ? DT_OK
                                    : dt_fail(e, x.result.status, 0, "control", "mock response");
}
static dt_status mock_claim(dt_device *d, unsigned i, int detach, dt_error *e) {
    struct mock_state *s = d->ctx->state;
    (void)detach;
    if (!connected(d))
        return dt_fail(e, DT_ERROR_NO_DEVICE, 0, "claim", "disconnected");
    if (i)
        return dt_fail(e, DT_ERROR_INVALID, 0, "claim", "mock has interface 0");
    if (s->owner)
        return dt_fail(e, DT_ERROR_BUSY, 0, "claim", "another owner");
    s->owner = d;
    return DT_OK;
}
static dt_status mock_reset(dt_device *d, dt_error *e) {
    struct mock_state *s = d->ctx->state;
    if (!connected(d))
        return dt_fail(e, DT_ERROR_NO_DEVICE, 0, "reset", "disconnected");
    if (s->owner)
        return dt_fail(e, DT_ERROR_BUSY, 0, "reset", "another handle claimed interface");
    s->now += 60000000;
    return DT_OK;
}
static dt_status mock_submit(dt_transfer *x, dt_error *e) {
    struct mock_state *s = x->dev->ctx->state;
    uint64_t latency;
    if (!connected(x->dev))
        return dt_fail(e, DT_ERROR_NO_DEVICE, 0, "submit", "disconnected");
    resolve(x, &latency);
    x->mock_hcd_done = latency == UINT64_MAX ? UINT64_MAX : s->now + latency;
    x->mock_done = latency == UINT64_MAX ? UINT64_MAX : x->mock_hcd_done + s->giveback;
    return DT_OK;
}
static dt_status mock_cancel(dt_transfer *x, dt_error *e) {
    struct mock_state *s = x->dev->ctx->state;
    if (x->ready || x->mock_done <= s->now)
        return dt_fail(e, DT_ERROR_NOT_PENDING, 0, "cancel", "already completed");
    /* Completion before giveback: accept cancel, preserve the real outcome. */
    if (x->mock_hcd_done <= s->now)
        return DT_OK;
    x->mock_done = s->now;
    x->ready = true;
    x->result.status = DT_ERROR_CANCELLED;
    x->result.kernel_status = -ENOENT;
    x->result.actual_length = 0;
    return DT_OK;
}
static dt_status mock_poll(dt_device *d, dt_transfer **out, dt_error *e) {
    struct mock_state *s = d->ctx->state;
    dt_transfer *best = NULL;
    for (dt_transfer *x = d->transfers; x; x = x->next) {
        if (!x->reaped && (x->ready || x->mock_done <= s->now) &&
            (!best || x->mock_done < best->mock_done))
            best = x;
    }
    if (!best)
        return dt_fail(e, DT_ERROR_AGAIN, 0, "reap", "no completion");
    best->ready = true;
    *out = best;
    return DT_OK;
}
static dt_status mock_wait(dt_device *d, int ms, dt_error *e) {
    struct mock_state *s = d->ctx->state;
    uint64_t next = ms < 0 ? UINT64_MAX : s->now + (uint64_t)ms * 1000000;
    for (dt_transfer *x = d->transfers; x; x = x->next)
        if (!x->reaped && x->mock_done < next)
            next = x->mock_done;
    if (next == UINT64_MAX)
        return dt_fail(e, DT_ERROR_AGAIN, 0, "wait", "no scheduled event in virtual time");
    s->now = next;
    return DT_OK;
}
static uint64_t mock_now(const dt_context *c) { return ((const struct mock_state *)c->state)->now; }
const struct dt_ops dt_mock_ops = {
    "mock",     mock_enumerate, mock_open,   mock_close, mock_control, mock_claim, mock_release,
    mock_reset, mock_submit,    mock_cancel, mock_poll,  mock_wait,    mock_now};

static int unhex(const char *s, uint8_t *out, size_t cap, size_t *length) {
    size_t n = strlen(s);
    if (n % 2 || n / 2 > cap)
        return -1;
    for (size_t i = 0; i < n; i += 2) {
        unsigned v = 0;
        for (unsigned j = 0; j < 2; j++) {
            unsigned char c = (unsigned char)s[i + j];
            unsigned x;
            if (c >= '0' && c <= '9')
                x = c - '0';
            else if (c >= 'a' && c <= 'f')
                x = c - 'a' + 10;
            else if (c >= 'A' && c <= 'F')
                x = c - 'A' + 10;
            else
                return -1;
            v = (v << 4) | x;
        }
        out[i / 2] = (uint8_t)v;
    }
    *length = n / 2;
    return 0;
}
dt_status dt_mock_load_replay(dt_context *c, const char *path, dt_error *e) {
    dt_context *tmp = NULL;
    struct mock_state *src, *dest;
    FILE *f;
    dt_status status = DT_OK;
    char line[8400], setup_hex[17], data_hex[8193], code_text[32], latency_text[32], extra;
    unsigned line_number = 1;
    if (mock_check(c, e))
        return DT_ERROR_INVALID;
    if (!path)
        return dt_fail(e, DT_ERROR_INVALID, 0, "replay", "path required");
    f = fopen(path, "r");
    if (!f)
        return dt_sysfail(e, "replay_open", errno);
    if (!fgets(line, sizeof(line), f) || strcmp(line, "DWC2_REPLAY 1\n")) {
        fclose(f);
        return dt_fail(e, DT_ERROR_INVALID, 0, "replay", "invalid version header");
    }
    status = dt_context_create("mock", &tmp, e);
    if (status) {
        fclose(f);
        return status;
    }
    while (fgets(line, sizeof(line), f)) {
        uint8_t setup_bytes[8], payload[4096];
        size_t sn = 0, pn = 0;
        uint64_t latency;
        long code;
        char *end;
        line_number++;
        if (!strchr(line, '\n') && !feof(f)) {
            status = DT_ERROR_INVALID;
            break;
        }
        if (sscanf(line, "%16s %31s %31s %8192s %c", setup_hex, code_text, latency_text, data_hex,
                   &extra) != 4 ||
            unhex(setup_hex, setup_bytes, 8, &sn) || sn != 8 ||
            (strcmp(data_hex, "-") && unhex(data_hex, payload, sizeof(payload), &pn))) {
            status = DT_ERROR_INVALID;
            break;
        }
        errno = 0;
        code = strtol(code_text, &end, 10);
        if (errno || *end || code > DT_OK || code < DT_ERROR_AGAIN) {
            status = DT_ERROR_INVALID;
            break;
        }
        errno = 0;
        latency = strtoull(latency_text, &end, 10);
        if (errno || *end || latency_text[0] == '-' || latency > UINT64_MAX / 4) {
            status = DT_ERROR_INVALID;
            break;
        }
        dt_setup setup = {setup_bytes[0], setup_bytes[1],
                          (uint16_t)(setup_bytes[2] | (setup_bytes[3] << 8)),
                          (uint16_t)(setup_bytes[4] | (setup_bytes[5] << 8)),
                          (uint16_t)(setup_bytes[6] | (setup_bytes[7] << 8))};
        if (setup.length > DT_MAX_CONTROL_LENGTH || pn > setup.length) {
            status = DT_ERROR_INVALID;
            break;
        }
        status =
            dt_mock_queue_response(tmp, &setup, (dt_status)code, payload, (uint32_t)pn, latency, e);
        if (status)
            break;
    }
    if (ferror(f))
        status = DT_ERROR_IO;
    fclose(f);
    src = tmp->state;
    dest = c->state;
    if (!status && src->queued == 0)
        status = DT_ERROR_INVALID;
    if (!status && src->queued + dest->queued > 128)
        status = DT_ERROR_INVALID;
    if (!status) {
        memcpy(dest->queue + dest->queued, src->queue, src->queued * sizeof(src->queue[0]));
        dest->queued += src->queued;
        src->queued = 0;
    }
    dt_context_destroy(tmp);
    return status ? dt_fail(e, status, 0, "replay", "invalid replay or capacity at line %u",
                            line_number)
                  : DT_OK;
}
