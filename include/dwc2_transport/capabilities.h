/* SPDX-License-Identifier: MIT */
#ifndef DWC2_TRANSPORT_CAPABILITIES_H
#define DWC2_TRANSPORT_CAPABILITIES_H
#include "device.h"
#ifdef __cplusplus
extern "C" {
#endif
#define DT_CAP_CONTROL (1u << 0)
#define DT_CAP_ASYNC_CONTROL (1u << 1)
#define DT_CAP_CANCEL (1u << 2)
#define DT_CAP_RESET (1u << 3)
#define DT_CAP_CLAIM (1u << 4)
#define DT_CAP_ASYNC_ENDPOINT (1u << 5)
#define DT_CAP_VIRTUAL_CLOCK (1u << 6)
/* Implemented operations, not a guarantee of permissions or device support. */
DT_API uint32_t dt_capabilities(const dt_device *);
#ifdef __cplusplus
}
#endif
#endif
