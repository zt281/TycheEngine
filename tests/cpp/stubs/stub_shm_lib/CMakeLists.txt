cmake_minimum_required(VERSION 3.16)
project(stub_shm_lib CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Get Tyche root for include paths
get_filename_component(TYCHE_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../../.." ABSOLUTE)

# Build as shared library
add_library(stub_shm_lib SHARED stub_shm_lib.cpp)

target_include_directories(stub_shm_lib PRIVATE
    ${TYCHE_ROOT}/src
)

# Set output directory to match test expectations
set_target_properties(stub_shm_lib PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY_DEBUG "${CMAKE_CURRENT_SOURCE_DIR}"
    LIBRARY_OUTPUT_DIRECTORY_DEBUG "${CMAKE_CURRENT_SOURCE_DIR}"
    ARCHIVE_OUTPUT_DIRECTORY_DEBUG "${CMAKE_CURRENT_SOURCE_DIR}"
    RUNTIME_OUTPUT_DIRECTORY_RELEASE "${CMAKE_CURRENT_SOURCE_DIR}"
    LIBRARY_OUTPUT_DIRECTORY_RELEASE "${CMAKE_CURRENT_SOURCE_DIR}"
    ARCHIVE_OUTPUT_DIRECTORY_RELEASE "${CMAKE_CURRENT_SOURCE_DIR}"
)

# Windows: export all symbols
set_target_properties(stub_shm_lib PROPERTIES WINDOWS_EXPORT_ALL_SYMBOLS ON)
