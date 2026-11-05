/* SPDX-License-Identifier: MIT */
#ifndef DT_INTERNAL_H
#define DT_INTERNAL_H
#include "dwc2_transport/transport.h"
#include <stdbool.h>
struct dt_ops {
    const char *name;
    dt_status (*enumerate)(dt_context *, dt_device_info **, size_t *, dt_error *);
    dt_status (*open)(dt_device *, dt_error *);
    void (*close)(dt_device *);
    dt_status (*control)(dt_device *, const dt_setup *, void *, uint32_t, size_t *, dt_error *);
    dt_status (*claim)(dt_device *, unsigned, int, dt_error *);
    dt_status (*release)(dt_device *, unsigned, int, dt_error *);
    dt_status (*reset)(dt_device *, dt_error *);
    dt_status (*submit)(dt_transfer *, dt_error *);
    dt_status (*cancel)(dt_transfer *, dt_error *);
    dt_status (*poll)(dt_device *, dt_transfer **, dt_error *);
    dt_status (*wait)(dt_device *, int, dt_error *);
    uint64_t (*now)(const dt_context *);
};
struct dt_context {
    const struct dt_ops *ops;
    void *state;
    dt_device *devices;
};
struct dt_device {
    dt_context *ctx;
    dt_device *next;
    dt_device_info info;
    int fd;
    void *state;
    bool claimed[256], detached[256];
    dt_transfer *transfers;
    unsigned pending, allocated;
    uint64_t generation;
};
struct dt_transfer {
    dt_device *dev;
    dt_transfer *next;
    dt_setup setup;
    dt_transfer_type type;
    uint8_t endpoint;
    unsigned interface_number;
    uint32_t length;
    uint8_t *wire; /* control setup + data, or endpoint data */
    void *backend;
    dt_completion result;
    uint64_t deadline, mock_hcd_done, mock_done;
    bool ready, reaped, timeout_requested;
};
void dt_transfer_cleanup(dt_device *);
uint8_t *dt_xfer_buffer(dt_transfer *);
dt_status dt_fail(dt_error *, dt_status, int, const char *, const char *, ...)
    __attribute__((format(printf, 5, 6)));
void dt_error_clear(dt_error *);
dt_status dt_errno_status(int);
dt_status dt_sysfail(dt_error *, const char *, int);
#ifdef __linux__
extern const struct dt_ops dt_linux_ops;
#endif
extern const struct dt_ops dt_mock_ops;
dt_status dt_mock_init(dt_context *, dt_error *);
void dt_mock_fini(dt_context *);
#endif
