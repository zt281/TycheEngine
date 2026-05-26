cmake_minimum_required(VERSION 3.16)
project(tyche_tests CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

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

if(TYCHE_BUILD_LIBZMQ)
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
include_directories(
    ${TYCHE_ROOT}/src
    ${THIRD_PARTY_DIR}/cppzmq
    ${THIRD_PARTY_DIR}/msgpack-c/include
    ${ZMQ_INCLUDE_DIR}
)

if(ZMQ_INCLUDE_DIRS)
    include_directories(${ZMQ_INCLUDE_DIRS})
endif()

# ── 源文件 ──
set(TYCHE_SRC_DIR "${TYCHE_ROOT}/src/tyche/cpp")

set(TYCHE_TEST_SOURCES
    test_ring_buffer.cpp
    test_topic_queue.cpp
    test_heartbeat_manager.cpp
    test_message.cpp
    test_types.cpp
    test_dead_letter_store.cpp
)

set(TYCHE_LIB_SOURCES
    ${TYCHE_SRC_DIR}/message.cpp
    ${TYCHE_SRC_DIR}/engine/topic_queue.cpp
    ${TYCHE_SRC_DIR}/engine/heartbeat_manager.cpp
    ${TYCHE_SRC_DIR}/engine/dead_letter_store.cpp
)

# ── 测试可执行文件 ──
add_executable(tyche_tests ${TYCHE_TEST_SOURCES} ${TYCHE_LIB_SOURCES})

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

# ── CTest 集成 ──
include(GoogleTest)
gtest_discover_tests(tyche_tests)
