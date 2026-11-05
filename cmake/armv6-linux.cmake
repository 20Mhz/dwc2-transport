set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR armv6)
set(CMAKE_C_COMPILER arm-linux-gnueabi-gcc)
set(CMAKE_AR arm-linux-gnueabi-ar)
set(CMAKE_C_FLAGS_INIT "-march=armv6kz -marm")
set(CMAKE_EXE_LINKER_FLAGS_INIT "-static")
# QEMU must reject ARMv7 instructions on the emulated ARM1176.
set(CMAKE_CROSSCOMPILING_EMULATOR qemu-arm-static;-cpu;arm1176)
