# msgpack-c: 使用内置 endian 检测，不依赖 Boost
add_definitions(-DMSGPACK_NO_BOOST)

# ── 项目根目录 ──
get_filename_component(TYCHE_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)

# ── GoogleTest via FetchContent ──
include(FetchContent)
FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG        v1.14.0
)
# For Windows: Prevent overriding the parent project's compiler/linker settings
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)

# ── 第三方库头文件 ──
set(THIRD_PARTY_DIR "${TYCHE_ROOT}/third_party")

# ── 查找或构建 libzmq ──
option(TYCHE_BUILD_LIBZMQ "Build libzmq from third_party source" OFF)

if(NOT TYCHE_BUILD_LIBZMQ)
    if(WIN32)
        find_path(ZMQ_INCLUDE_DIR zmq.h
            HINTS ENV ZMQ_DIR
            PATH_SUFFIXES include)
        find_library(ZMQ_LIBRARY
            NAMES zmq libzmq
            HINTS ENV ZMQ_DIR
            PATH_SUFFIXES lib)
        if(NOT ZMQ_INCLUDE_DIR OR NOT ZMQ_LIBRARY)
            find_package(PkgConfig QUIET)
            if(PkgConfig_FOUND)
                pkg_check_modules(ZMQ libzmq)
            endif()
        endif()
        if(NOT ZMQ_INCLUDE_DIR AND NOT ZMQ_FOUND)
            message(STATUS "libzmq not found. Falling back to building from source.")
            set(TYCHE_BUILD_LIBZMQ ON)
        endif()
    else()
        find_package(PkgConfig REQUIRED)
        pkg_check_modules(ZMQ libzmq)
        if(NOT ZMQ_FOUND)
            set(TYCHE_BUILD_LIBZMQ ON)
        endif()
    endif()
endif()

# libzmq is already built by parent src/tyche/cpp/CMakeLists.txt;
# we just reuse its variables here.  Do NOT add_subdirectory libzmq again.
if(TYCHE_BUILD_LIBZMQ)
    set(ZMQ_INCLUDE_DIR "${THIRD_PARTY_DIR}/libzmq/include")
    set(ZMQ_LIBRARY libzmq-static)
    # Add libzmq subdirectory for building (tests CMake is standalone)
    # Skip if target already exists from parent project to avoid binary dir conflict
    if(NOT TARGET libzmq-static)
        set(ZMQ_BUILD_TESTS OFF CACHE BOOL "" FORCE)
        set(BUILD_TESTS OFF CACHE BOOL "" FORCE)
        set(BUILD_SHARED OFF CACHE BOOL "" FORCE)
        set(BUILD_STATIC ON CACHE BOOL "" FORCE)
        set(WITH_DOCS OFF CACHE BOOL "" FORCE)
        set(WITH_PERF_TOOL OFF CACHE BOOL "" FORCE)
        add_subdirectory("${THIRD_PARTY_DIR}/libzmq" "${CMAKE_BINARY_DIR}/libzmq" EXCLUDE_FROM_ALL)
    endif()
endif()

# ── CTP SDK 头文件目录 ──
set(CTP_SDK_DIR "${TYCHE_ROOT}/src/modules/ctp_gateway_cpp/include/ctp")

# ── Include 路径 ──
include_directories(
    ${TYCHE_ROOT}/src
    ${THIRD_PARTY_DIR}/cppzmq
    ${THIRD_PARTY_DIR}/msgpack-c/include
    ${THIRD_PARTY_DIR}
    ${ZMQ_INCLUDE_DIR}
    ${CTP_SDK_DIR}
)

if(ZMQ_INCLUDE_DIRS)
    include_directories(${ZMQ_INCLUDE_DIRS})
endif()

# ── 源文件 ──
set(TYCHE_SRC_DIR "${TYCHE_ROOT}/src/tyche/cpp")

set(CTP_SRC_DIR "${TYCHE_ROOT}/src/modules/ctp_gateway_cpp/src")

set(TYCHE_TEST_SOURCES
    test_ring_buffer.cpp
    test_topic_queue.cpp
    test_heartbeat_manager.cpp
    test_message.cpp
    test_types.cpp
    test_dead_letter_store.cpp
    test_shared_memory_queue.cpp
    test_dynamic_library.cpp
    test_flat_message.cpp
    test_adaptive_spin.cpp
    test_fast_clock.cpp
    test_object_pool.cpp
    test_topic_queue_index.cpp
    test_rcu_snapshot.cpp
    test_thread_affinity.cpp
    test_string_intern.cpp
    test_sharded_topic_map.cpp
    test_engine.cpp
    test_config.cpp
    test_quote_validator.cpp
    test_md_spi.cpp
    test_td_spi.cpp
    test_ctp_loader.cpp
    test_shared_memory_bridge.cpp
    test_ctp_loader_integration.cpp
    test_engine_integration.cpp
)

set(CTP_LIB_SOURCES
    ${CTP_SRC_DIR}/config.cpp
    ${CTP_SRC_DIR}/md_spi.cpp
    ${CTP_SRC_DIR}/td_spi.cpp
    ${CTP_SRC_DIR}/ctp_loader.cpp
)

set(TYCHE_LIB_SOURCES
    ${TYCHE_SRC_DIR}/message.cpp
    ${TYCHE_SRC_DIR}/engine/topic_queue.cpp
    ${TYCHE_SRC_DIR}/engine/sharded_topic_map.cpp
    ${TYCHE_SRC_DIR}/engine/heartbeat_manager.cpp
    ${TYCHE_SRC_DIR}/engine/dead_letter_store.cpp
    ${TYCHE_SRC_DIR}/engine/shared_memory_queue.cpp
    ${TYCHE_SRC_DIR}/engine/dynamic_library.cpp
    ${TYCHE_SRC_DIR}/engine/fast_clock.cpp
    ${TYCHE_SRC_DIR}/engine/thread_affinity.cpp
    ${TYCHE_SRC_DIR}/engine/engine.cpp
    ${TYCHE_SRC_DIR}/engine/shared_memory_bridge.cpp
)

# ── 测试可执行文件 ──
add_executable(tyche_tests ${TYCHE_TEST_SOURCES} ${TYCHE_LIB_SOURCES} ${CTP_LIB_SOURCES})

target_link_libraries(tyche_tests PRIVATE
    GTest::gtest_main
    ${ZMQ_LIBRARY}
)

if(ZMQ_LIBRARIES)
    target_link_libraries(tyche_tests PRIVATE ${ZMQ_LIBRARIES})
endif()

if(WIN32)
    target_link_libraries(tyche_tests PRIVATE ws2_32 iphlpapi)
else()
    target_link_libraries(tyche_tests PRIVATE pthread)
endif()

# ── Performance benchmark executables ──
# Note: Most perf benchmarks are defined in src/tyche/cpp/CMakeLists.txt
# Only ring_buffer_bench is defined here as it has no TYCHE_LIB dependencies
add_executable(ring_buffer_bench
    ../perf/ring_buffer_bench.cpp
)

target_link_libraries(ring_buffer_bench PRIVATE
    ${ZMQ_LIBRARY}
)
if(ZMQ_LIBRARIES)
    target_link_libraries(ring_buffer_bench PRIVATE ${ZMQ_LIBRARIES})
endif()

if(WIN32)
    target_link_libraries(ring_buffer_bench PRIVATE ws2_32 iphlpapi)
else()
    target_link_libraries(ring_buffer_bench PRIVATE pthread)
endif()

# ── CTest 集成 ──
include(GoogleTest)
gtest_discover_tests(tyche_tests)

# ── Stub libraries for integration tests ──
add_subdirectory(stubs/stub_shm_lib EXCLUDE_FROM_ALL)
add_subdirectory(stubs/stub_ctp_dll EXCLUDE_FROM_ALL)
