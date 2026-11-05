/* SPDX-License-Identifier: MIT */
#ifndef DWC2_TRANSPORT_H
#define DWC2_TRANSPORT_H
#include "capabilities.h"
#include "device.h"
#ifdef __cplusplus
extern "C" {
#endif
#define DT_API_MAJOR 1
#define DT_API_MINOR 0
#define DT_VERSION "1.2.0"
#define DT_MAX_CONTROL_LENGTH 4096u
#define DT_MAX_ENDPOINT_LENGTH (1024u * 1024u)
/* ABI major in high 16 bits; minor in low 16. */
DT_API uint32_t dt_api_version(void);
DT_API const char *dt_version(void);
/* backend: "linux-usbfs" (Linux only) or "mock". Independent contexts;
 * no shared mutable globals or background threads. Serialize all calls on a
 * context and its children. Independent contexts can be used concurrently. */
DT_API dt_status dt_context_create(const char *backend, dt_context **out, dt_error *);
/* Closes all children. Call from normal code, never a signal handler. */
DT_API void dt_context_destroy(dt_context *);
DT_API const char *dt_backend_name(const dt_context *);
typedef struct dt_setup {
    uint8_t request_type, request;
    uint16_t value, index, length; /* host byte order */
} dt_setup;
/* timeout_ms=0: no deadline. IN/OUT determined by request_type bit 7.
 * data capacity >= setup.length; actual initialized to 0 even on failure. */
DT_API dt_status dt_control(dt_device *, const dt_setup *, void *data, uint32_t timeout_ms,
                            size_t *actual, dt_error *);
/* Standard GET_DESCRIPTOR with a finite 1000ms timeout; no interface claim. */
DT_API dt_status dt_get_descriptor(dt_device *, uint8_t type, uint8_t index, uint16_t language,
                                   void *buffer, uint16_t length, size_t *actual, dt_error *);
/* Asynchronous objects are owned by the device until dt_transfer_free().
 * Submit copies OUT data immediately. IN data is SDK-owned and readable only
 * after reap, until free/close. Up to 64 allocated transfers per device. */
typedef struct dt_transfer dt_transfer;
typedef enum dt_transfer_type {
    DT_TRANSFER_CONTROL = 0,
    DT_TRANSFER_BULK = 1,
    DT_TRANSFER_INTERRUPT = 2
} dt_transfer_type;
typedef struct dt_completion {
    dt_status status;
    int kernel_status; /* negative kernel errno; 0 for mock success */
    size_t actual_length;
    uint64_t submitted_ns, cancelled_ns, reaped_ns;
    void *user;
} dt_completion;
DT_API dt_status dt_submit_control(dt_device *, const dt_setup *, const void *out_data,
                                   uint32_t timeout_ms, void *user, dt_transfer **, dt_error *);
/* Requires an explicitly claimed interface. No implicit claim/detach.
 * Only bulk/interrupt endpoints 1..15, IN or OUT, are supported. */
DT_API dt_status dt_submit_endpoint(dt_device *, unsigned interface_number, dt_transfer_type,
                                    uint8_t endpoint, const void *out_data, uint32_t length,
                                    uint32_t timeout_ms, void *user, dt_transfer **, dt_error *);
/* Accepted cancellation may race a successful completion. Reap is
 * authoritative. NOT_PENDING still requires reaping unless it was already
 * reaped. */
DT_API dt_status dt_cancel(dt_transfer *, dt_error *);
/* wait_ms=0: poll, -1: wait indefinitely, >0: bounded wait. AGAIN means no
 * completion; it does not cancel anything. Call reap to service deadlines:
 * timeout_ms on submit does not start a background timer. Completion already
 * queued at service time wins over a late timeout. */
DT_API dt_status dt_reap(dt_device *, int wait_ms, dt_transfer **out, dt_error *);
DT_API const dt_completion *dt_transfer_result(const dt_transfer *);
DT_API const uint8_t *dt_transfer_data(const dt_transfer *);
DT_API dt_status dt_transfer_free(dt_transfer *, dt_error *); /* BUSY until reaped */
DT_API uint64_t dt_now_ns(const dt_context *);                /* monotonic or virtual */
#ifdef __cplusplus
}
#endif
#endif
