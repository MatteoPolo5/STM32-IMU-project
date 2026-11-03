include(FetchContent)

# Register definitions and Cortex-M core headers only (no HAL / no vendor drivers).
FetchContent_Declare(cmsis_core
  GIT_REPOSITORY https://github.com/ARM-software/CMSIS_5.git
  GIT_TAG        5.9.0
  GIT_SHALLOW    TRUE
  SOURCE_SUBDIR  _no_cmake_here)
FetchContent_Declare(cmsis_device_f4
  GIT_REPOSITORY https://github.com/STMicroelectronics/cmsis_device_f4.git
  GIT_TAG        v2.6.10
  GIT_SHALLOW    TRUE
  SOURCE_SUBDIR  _no_cmake_here)
FetchContent_MakeAvailable(cmsis_core cmsis_device_f4)

# Tunables (see firmware/include/config.hpp). Leave empty to use the defaults.
set(SAMPLE_RATE_HZ "" CACHE STRING "IMU sampling rate in Hz (default 1000)")
set(I2C_CLOCK_HZ   "" CACHE STRING "I2C clock in Hz (default 400000)")
set(UART_BAUD      "" CACHE STRING "UART baud rate (default 460800)")
option(USE_HSE_BYPASS "Use the 8 MHz ST-LINK MCO as clock source (falls back to HSI)" OFF)

execute_process(COMMAND git describe --tags --always --dirty
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  OUTPUT_VARIABLE GIT_DESCRIBE OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
if(NOT GIT_DESCRIBE)
  set(GIT_DESCRIBE "${PROJECT_VERSION}")
endif()

add_executable(imu_daq
  src/main.cpp
  src/sysclk.cpp
  src/uart.cpp
  src/i2c.cpp
  src/mpu6050.cpp
  src/daq.cpp
  src/startup_stm32f446xx.cpp)
set_target_properties(imu_daq PROPERTIES SUFFIX ".elf")

target_include_directories(imu_daq PRIVATE
  include src
  ${cmsis_core_SOURCE_DIR}/CMSIS/Core/Include
  ${cmsis_device_f4_SOURCE_DIR}/Include)

target_compile_definitions(imu_daq PRIVATE
  STM32F446xx
  FW_VERSION="${GIT_DESCRIBE}"
  USE_HSE_BYPASS=$<BOOL:${USE_HSE_BYPASS}>)
foreach(var SAMPLE_RATE_HZ I2C_CLOCK_HZ UART_BAUD)
  if(NOT "${${var}}" STREQUAL "")
    target_compile_definitions(imu_daq PRIVATE ${var}=${${var}})
  endif()
endforeach()

set(MCU_FLAGS -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard)
target_compile_options(imu_daq PRIVATE
  ${MCU_FLAGS}
  -Wall -Wextra -Wshadow -Wdouble-promotion
  -ffunction-sections -fdata-sections
  -fno-exceptions -fno-rtti -fno-threadsafe-statics -fno-use-cxa-atexit
  $<$<CONFIG:Debug>:-Og -g3>
  $<$<CONFIG:Release>:-O2 -g>
  $<$<CONFIG:MinSizeRel>:-Os -g>)

target_link_options(imu_daq PRIVATE
  ${MCU_FLAGS}
  -T${CMAKE_CURRENT_SOURCE_DIR}/linker/STM32F446RETx_FLASH.ld
  --specs=nano.specs --specs=nosys.specs -nostartfiles
  -Wl,--gc-sections
  -Wl,-Map=$<TARGET_FILE_DIR:imu_daq>/imu_daq.map
  -Wl,--print-memory-usage)

add_custom_command(TARGET imu_daq POST_BUILD
  COMMAND ${CMAKE_OBJCOPY} -O binary $<TARGET_FILE:imu_daq> $<TARGET_FILE_DIR:imu_daq>/imu_daq.bin
  COMMAND ${CMAKE_OBJCOPY} -O ihex   $<TARGET_FILE:imu_daq> $<TARGET_FILE_DIR:imu_daq>/imu_daq.hex
  COMMAND ${CMAKE_SIZE} $<TARGET_FILE:imu_daq>)

# `cmake --build --preset firmware --target flash` programs the board through ST-LINK.
add_custom_target(flash
  COMMAND openocd -f interface/stlink.cfg -f target/stm32f4x.cfg
          -c "program $<TARGET_FILE:imu_daq> verify reset exit"
  DEPENDS imu_daq
  COMMENT "Flashing with OpenOCD")
