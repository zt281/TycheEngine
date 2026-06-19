# msgpack-c: 使用内置 endian 检测，不依赖 Boost
add_definitions(-DMSGPACK_NO_BOOST)

# ── 项目根目录 ──
# 从 src/tyche/cpp/ 回到项目根: ../../..
get_filename_component(TYCHE_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)

# ── 第三方库头文件 ──
set(THIRD_PARTY_DIR "${TYCHE_ROOT}/third_party")

# ── 查找或构建 libzmq ──
# 优先使用系统已安装的 libzmq，如果找不到则从 third_party 源码构建
option(TYCHE_BUILD_LIBZMQ "Build libzmq from third_party source" OFF)

if(NOT TYCHE_BUILD_LIBZMQ)
    if(WIN32)
        # Windows: 尝试查找预编译的 libzmq
        # 用户可通过设置 ZMQ_DIR 环境变量指定安装路径
        find_path(ZMQ_INCLUDE_DIR zmq.h
            HINTS ENV ZMQ_DIR
            PATH_SUFFIXES include)
        find_library(ZMQ_LIBRARY
            NAMES zmq libzmq
            HINTS ENV ZMQ_DIR
            PATH_SUFFIXES lib)
        if(NOT ZMQ_INCLUDE_DIR OR NOT ZMQ_LIBRARY)
            message(STATUS "libzmq not found via find_path, trying pkg-config...")
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
            message(STATUS "libzmq not found via pkg-config. Falling back to building from source.")
            set(TYCHE_BUILD_LIBZMQ ON)
        endif()
    endif()
endif()

if(TYCHE_BUILD_LIBZMQ)
    # 从 third_party/libzmq 源码构建
    message(STATUS "Building libzmq from ${THIRD_PARTY_DIR}/libzmq")
    set(ZMQ_BUILD_TESTS OFF CACHE BOOL "" FORCE)
    set(BUILD_TESTS OFF CACHE BOOL "" FORCE)
    set(BUILD_SHARED OFF CACHE BOOL "" FORCE)
    set(BUILD_STATIC ON CACHE BOOL "" FORCE)
    set(WITH_DOCS OFF CACHE BOOL "" FORCE)
    set(WITH_PERF_TOOL OFF CACHE BOOL "" FORCE)
    add_subdirectory("${THIRD_PARTY_DIR}/libzmq" "${CMAKE_BINARY_DIR}/libzmq" EXCLUDE_FROM_ALL)
    set(ZMQ_INCLUDE_DIR "${THIRD_PARTY_DIR}/libzmq/include")
    set(ZMQ_LIBRARY libzmq-static)
endif()

# ── Include 路径 ──
# 布局:
#   third_party/cppzmq/zmq.hpp          (header-only, 根目录)
#   third_party/msgpack-c/include/msgpack.hpp (header-only)
#   third_party/libzmq/include/zmq.h
include_directories(
    ${TYCHE_ROOT}/src                       # 让 #include "tyche/cpp/types.h" 工作
    ${THIRD_PARTY_DIR}/cppzmq              # zmq.hpp, zmq_addon.hpp
    ${THIRD_PARTY_DIR}/msgpack-c/include   # msgpack.hpp
    ${THIRD_PARTY_DIR}                     # nlohmann_json.hpp
    ${ZMQ_INCLUDE_DIR}                     # zmq.h
)

# 如果通过 pkg-config 找到，添加其 include 目录
if(ZMQ_INCLUDE_DIRS)
    include_directories(${ZMQ_INCLUDE_DIRS})
endif()

# ── Engine 可执行文件 ──
add_executable(tyche_engine
    engine/main.cpp
    engine/engine.cpp
    engine/topic_queue.cpp
    engine/sharded_topic_map.cpp
    engine/heartbeat_manager.cpp
    engine/dead_letter_store.cpp
    engine/shared_memory_queue.cpp
    engine/dynamic_library.cpp
    engine/shared_memory_bridge.cpp
    engine/fast_clock.cpp
    engine/thread_affinity.cpp
    message.cpp
)

target_link_libraries(tyche_engine PRIVATE
    ${ZMQ_LIBRARY}
)
if(ZMQ_LIBRARIES)
    target_link_libraries(tyche_engine PRIVATE ${ZMQ_LIBRARIES})
endif()

if(WIN32)
    target_link_libraries(tyche_engine PRIVATE ws2_32 iphlpapi)
else()
    target_link_libraries(tyche_engine PRIVATE pthread)
endif()

# ── Module 静态库 ──
add_library(tyche_module STATIC
    module.cpp
    message.cpp
)

target_link_libraries(tyche_module PUBLIC
    ${ZMQ_LIBRARY}
)
if(ZMQ_LIBRARIES)
    target_link_libraries(tyche_module PUBLIC ${ZMQ_LIBRARIES})
endif()

if(WIN32)
    target_link_libraries(tyche_module PUBLIC ws2_32 iphlpapi)
else()
    target_link_libraries(tyche_module PUBLIC pthread)
endif()

# ── Perf benchmark executables ──
add_executable(serialization_bench
    ${TYCHE_ROOT}/tests/perf/serialization_bench.cpp
    message.cpp
)

add_executable(flat_message_bench
    ${TYCHE_ROOT}/tests/perf/flat_message_bench.cpp
    message.cpp
)

add_executable(shm_bridge_bench
    ${TYCHE_ROOT}/tests/perf/shm_bridge_bench.cpp
    engine/shared_memory_queue.cpp
    engine/dynamic_library.cpp
    message.cpp
)

add_executable(alloc_bench
    ${TYCHE_ROOT}/tests/perf/alloc_bench.cpp
    engine/topic_queue.cpp
    engine/sharded_topic_map.cpp
    message.cpp
)

add_executable(e2e_latency_bench
    ${TYCHE_ROOT}/tests/perf/e2e_latency_bench.cpp
    message.cpp
    engine/fast_clock.cpp
)

add_executable(ctp_dispatch_bench
    ${TYCHE_ROOT}/tests/perf/ctp_dispatch_bench.cpp
    engine/fast_clock.cpp
)

add_executable(topic_queue_bench
    ${TYCHE_ROOT}/tests/perf/topic_queue_bench.cpp
    engine/topic_queue.cpp
    engine/sharded_topic_map.cpp
    message.cpp
)

foreach(bench_target serialization_bench flat_message_bench shm_bridge_bench alloc_bench e2e_latency_bench ctp_dispatch_bench topic_queue_bench)
    target_link_libraries(${bench_target} PRIVATE ${ZMQ_LIBRARY})
    if(ZMQ_LIBRARIES)
        target_link_libraries(${bench_target} PRIVATE ${ZMQ_LIBRARIES})
    endif()
    if(WIN32)
        target_link_libraries(${bench_target} PRIVATE ws2_32 iphlpapi)
    else()
        target_link_libraries(${bench_target} PRIVATE pthread)
    endif()
endforeach()

# ── 安装规则 ──
install(TARGETS tyche_engine DESTINATION bin)
install(TARGETS tyche_module DESTINATION lib)
install(FILES
    types.h
    message.h
    module.h
    DESTINATION include/tyche/cpp)
install(FILES
    engine/engine.h
    engine/heartbeat_manager.h
    engine/dead_letter_store.h
    engine/topic_queue.h
    engine/ring_buffer.h
    engine/shared_memory_queue.h
    engine/dynamic_library.h
    engine/shared_memory_bridge.h
    engine/module_interface.h
    engine/adaptive_spin.h
    engine/fast_clock.h
    engine/object_pool.h
    engine/topic_queue_index.h
    engine/rcu_snapshot.h
    engine/thread_affinity.h
    DESTINATION include/tyche/cpp/engine)
