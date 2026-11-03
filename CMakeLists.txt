cmake_minimum_required(VERSION 3.21)
project(nucleo-f446re-imu-daq VERSION 0.1.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if(CMAKE_CROSSCOMPILING)
  add_subdirectory(firmware)          # the firmware for the target
else()
  enable_testing()
  add_subdirectory(tests)             # host-side unit tests of the portable core
endif()
