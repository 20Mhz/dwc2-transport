/* SPDX-License-Identifier: MIT */
#ifndef DT_MOCK_H
#define DT_MOCK_H
#include "transport.h"
#ifdef __cplusplus
extern "C" {
#endif
/* All functions reject non-mock contexts. One deterministic virtual device,
 * 1209:0001 at mock:1:2. Queue responses FIFO (max 128); payload is copied.
 * NULL match matches any transfer; otherwise matches all setup fields of
 * control transfers. Unprogrammed control descriptors/status succeed;
 * other control requests STALL; endpoint requests remain pending. */
DT_API dt_status dt_mock_queue_response(dt_context *, const dt_setup *match, dt_status,
                                        const void *data, uint32_t length, uint64_t latency_ns,
                                        dt_error *);
DT_API dt_status dt_mock_set_timing(dt_context *, uint64_t latency_ns, uint64_t giveback_delay_ns,
                                    dt_error *);
DT_API dt_status dt_mock_advance(dt_context *, uint64_t nanoseconds, dt_error *);
/* Disconnect completes in-flight work with NO_DEVICE and invalidates existing
 * handles permanently. Reconnect requires discovery/open of a new handle. */
DT_API dt_status dt_mock_set_connected(dt_context *, int connected, dt_error *);
/* Load replay v1 atomically: DWC2_REPLAY 1 header, then rows containing
 * 16 setup hex digits, numeric dt_status, latency_ns, payload hex or '-'.
 * At most 128 queued records. No transfer is executed by the loader. */
DT_API dt_status dt_mock_load_replay(dt_context *, const char *path, dt_error *);
#ifdef __cplusplus
}
#endif
#endif
