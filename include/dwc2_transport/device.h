/* SPDX-License-Identifier: MIT */
#ifndef DWC2_TRANSPORT_DEVICE_H
#define DWC2_TRANSPORT_DEVICE_H
#include "errors.h"
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct dt_context dt_context;
typedef struct dt_device dt_device;
typedef enum dt_speed {
    DT_SPEED_UNKNOWN = 0,
    DT_SPEED_LOW = 1,
    DT_SPEED_FULL = 2,
    DT_SPEED_HIGH = 3,
    DT_SPEED_WIRELESS = 4,
    DT_SPEED_SUPER = 5,
    DT_SPEED_SUPER_PLUS = 6
} dt_speed;
typedef struct dt_device_info {
    uint8_t bus, address, device_class, port_count;
    uint16_t vendor_id, product_id;
    dt_speed speed;
    uint8_t ports[7];
    char path[128];
    char sysfs_name[64];
    char driver[128]; /* comma-separated interface driver names; empty if unknown
                       */
    char controller[64];
} dt_device_info;
DT_API const char *dt_speed_name(dt_speed speed);
/* A snapshot allocated by the SDK; free with dt_device_list_free(). */
DT_API dt_status dt_enumerate(dt_context *, dt_device_info **items, size_t *count, dt_error *);
DT_API void dt_device_list_free(dt_device_info *);
/* Open an exact path returned by discovery. No implicit driver detachment. */
DT_API dt_status dt_open(dt_context *, const dt_device_info *, dt_device **out, dt_error *);
/* Cancels pending kernel work, closes fd, then frees all owned transfers.
 * Every transfer and data pointer belonging to this device becomes invalid. */
DT_API void dt_close(dt_device *);
DT_API const dt_device_info *dt_device_get_info(const dt_device *);
/* detach=1 is explicit; close automatically attempts to restore drivers
 * detached by this handle. A reset can drop claims: release before reset. */
DT_API dt_status dt_claim_interface(dt_device *, unsigned interface_number, int detach, dt_error *);
DT_API dt_status dt_release_interface(dt_device *, unsigned interface_number, dt_error *);
/* Refuses pending transfers or claimed interfaces. Rediscover/reopen on
 * NO_DEVICE. */
DT_API dt_status dt_reset(dt_device *, dt_error *);
#ifdef __cplusplus
}
#endif
#endif
