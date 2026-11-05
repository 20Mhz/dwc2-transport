/* SPDX-License-Identifier: MIT */
#ifndef DWC2_TRANSPORT_ERRORS_H
#define DWC2_TRANSPORT_ERRORS_H
#if defined(__GNUC__) || defined(__clang__)
#define DT_API __attribute__((visibility("default")))
#else
#define DT_API
#endif
#ifdef __cplusplus
extern "C" {
#endif
typedef enum dt_status {
    DT_OK = 0,
    DT_ERROR_INVALID = -1,
    DT_ERROR_NO_DEVICE = -2,
    DT_ERROR_ACCESS = -3,
    DT_ERROR_BUSY = -4,
    DT_ERROR_TIMEOUT = -5,
    DT_ERROR_STALL = -6,
    DT_ERROR_PROTOCOL = -7,
    DT_ERROR_OVERFLOW = -8,
    DT_ERROR_CANCELLED = -9,
    DT_ERROR_NOT_PENDING = -10,
    DT_ERROR_IO = -11,
    DT_ERROR_NOMEM = -12,
    DT_ERROR_UNSUPPORTED = -13,
    DT_ERROR_AGAIN = -14
} dt_status;
typedef struct dt_error {
    dt_status status;
    int system_errno;
    char operation[32];
    char message[160];
} dt_error;
DT_API const char *dt_status_name(dt_status status);
#ifdef __cplusplus
}
#endif
#endif
