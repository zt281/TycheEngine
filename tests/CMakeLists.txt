# 测试根 CMakeLists.txt
# 统一组织所有 C++ 测试
# 各子目录（cpp/、unit/ctp_gateway/）也可独立构建

if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
    cmake_minimum_required(VERSION 3.16)
    project(tyche_tests_root CXX)
    set(CMAKE_CXX_STANDARD 17)
    set(CMAKE_CXX_STANDARD_REQUIRED ON)
    if(MSVC)
        add_compile_options(/utf-8)
    endif()
endif()

enable_testing()

add_subdirectory(cpp)
add_subdirectory(unit/ctp_gateway)
