cmake_minimum_required(VERSION 3.16)
project(TycheEngine CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# MSVC: UTF-8 编码处理源文件，避免 C4819 警告
if(MSVC)
    add_compile_options(/utf-8)
endif()

# ── 自动检测 Visual Studio 生成器（仅限 Windows）───────────────
# CMake 3.16+ 支持通过 -G 指定生成器。若用户未显式指定，且当前为 Windows
# 平台，则尝试用 vswhere 自动查找最新可用的 Visual Studio 实例。
if(WIN32 AND NOT CMAKE_GENERATOR MATCHES "Visual Studio")
    set(VSWHERE_PATH "C:/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe")
    if(EXISTS ${VSWHERE_PATH})
        execute_process(
            COMMAND ${VSWHERE_PATH} -latest -prerelease -property catalog_productLineVersion
            OUTPUT_VARIABLE VS_PRODUCT_LINE
            OUTPUT_STRIP_TRAILING_WHITESPACE
            ERROR_QUIET
            RESULT_VARIABLE VSWHERE_RESULT
        )
        if(VSWHERE_RESULT EQUAL 0 AND VS_PRODUCT_LINE)
            execute_process(
                COMMAND ${VSWHERE_PATH} -latest -prerelease -property installationVersion
                OUTPUT_VARIABLE VS_INSTALL_VERSION
                OUTPUT_STRIP_TRAILING_WHITESPACE
                ERROR_QUIET
            )
            # 提取主版本号（如 18.5.2 -> 18）
            string(REGEX MATCH "^([0-9]+)" VS_MAJOR "${VS_INSTALL_VERSION}")
            if(VS_MAJOR)
                set(CMAKE_GENERATOR "Visual Studio ${VS_PRODUCT_LINE} ${VS_MAJOR}" CACHE INTERNAL "Detected VS generator" FORCE)
                message(STATUS "Auto-detected Visual Studio generator: ${CMAKE_GENERATOR}")
            endif()
        endif()
    endif()
endif()

# 统一产物输出目录（所有子项目共享）
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_SOURCE_DIR}/runtime/engine)
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_SOURCE_DIR}/runtime/engine)
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_SOURCE_DIR}/runtime/engine)

# 按配置区分子目录（Debug / Release / RelWithDebInfo / MinSizeRel）
foreach(OUTPUTCONFIG ${CMAKE_CONFIGURATION_TYPES})
    string(TOUPPER ${OUTPUTCONFIG} OUTPUTCONFIG_UPPER)
    set(CMAKE_RUNTIME_OUTPUT_DIRECTORY_${OUTPUTCONFIG_UPPER} ${CMAKE_SOURCE_DIR}/runtime/engine)
    set(CMAKE_LIBRARY_OUTPUT_DIRECTORY_${OUTPUTCONFIG_UPPER} ${CMAKE_SOURCE_DIR}/runtime/engine)
    set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY_${OUTPUTCONFIG_UPPER} ${CMAKE_SOURCE_DIR}/runtime/engine)
endforeach()

# ── 子项目 ──────────────────────────────────────────────────────
add_subdirectory(src/tyche/cpp)
add_subdirectory(src/modules/ctp_gateway_cpp)
add_subdirectory(tests/cpp)
