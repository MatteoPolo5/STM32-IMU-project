include(FetchContent)
FetchContent_Declare(googletest
  GIT_REPOSITORY https://github.com/google/googletest.git
  GIT_TAG        v1.14.0
  GIT_SHALLOW    TRUE)
set(INSTALL_GTEST OFF CACHE BOOL "" FORCE)
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)

find_package(Threads REQUIRED)

# The portable core (protocol, ring buffer, config checks) has no hardware
# dependency, so it is unit-tested natively on the development machine.
add_executable(core_tests test_protocol.cpp test_ring_buffer.cpp test_config.cpp)
target_include_directories(core_tests PRIVATE ${CMAKE_SOURCE_DIR}/firmware/include)
target_compile_definitions(core_tests PRIVATE
  GOLDEN_VECTOR_FILE="${CMAKE_CURRENT_SOURCE_DIR}/golden/frame_vector.txt")
target_compile_options(core_tests PRIVATE -Wall -Wextra -Wshadow)
target_link_libraries(core_tests PRIVATE GTest::gtest_main Threads::Threads)

include(GoogleTest)
gtest_discover_tests(core_tests)
