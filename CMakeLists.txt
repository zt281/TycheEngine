cmake_minimum_required(VERSION 3.16)
project(TycheEngine CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# MSVC: UTF-8 编码处理源文件，避免 C4819 警告
if(MSVC)
    add_compile_options(/utf-8)
endif()

# ── 覆盖率支持 ──────────────────────────────────────────────────────
option(TYCHE_ENABLE_COVERAGE "Enable code coverage reporting" OFF)
if(TYCHE_ENABLE_COVERAGE)
    if(MSVC)
        message(STATUS "Code coverage enabled for MSVC: adding /PROFILE linker option")
        # /PROFILE enables code coverage profiling with VS Enterprise/CodeCoverage
        add_link_options(/PROFILE)
    else()
        message(STATUS "Code coverage enabled: adding -fprofile-arcs -ftest-coverage")
        add_compile_options(-fprofile-arcs -ftest-coverage)
        add_link_options(-fprofile-arcs -ftest-coverage)
    endif()
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

# 统一产物输出目录（按平台分离）
if(WIN32)
    set(TYCHE_RUNTIME_DIR "${CMAKE_SOURCE_DIR}/runtime/win")
else()
    set(TYCHE_RUNTIME_DIR "${CMAKE_SOURCE_DIR}/runtime/linux")
endif()

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${TYCHE_RUNTIME_DIR})
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${TYCHE_RUNTIME_DIR})
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${TYCHE_RUNTIME_DIR})

# 按配置区分子目录（Debug / Release / RelWithDebInfo / MinSizeRel）
foreach(OUTPUTCONFIG ${CMAKE_CONFIGURATION_TYPES})
    string(TOUPPER ${OUTPUTCONFIG} OUTPUTCONFIG_UPPER)
    set(CMAKE_RUNTIME_OUTPUT_DIRECTORY_${OUTPUTCONFIG_UPPER} ${TYCHE_RUNTIME_DIR})
    set(CMAKE_LIBRARY_OUTPUT_DIRECTORY_${OUTPUTCONFIG_UPPER} ${TYCHE_RUNTIME_DIR})
    set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY_${OUTPUTCONFIG_UPPER} ${TYCHE_RUNTIME_DIR})
endforeach()

# ── 子项目 ──────────────────────────────────────────────────────
add_subdirectory(src/tyche/cpp)
add_subdirectory(src/modules/ctp_gateway_cpp)
add_subdirectory(tests)

# ── 覆盖率报告目标 ───────────────────────────────
if(TYCHE_ENABLE_COVERAGE)
    if(MSVC)
        # Windows: provide instructions for VS Enterprise CodeCoverage or OpenCppCoverage
        add_custom_target(coverage
            COMMAND ${CMAKE_COMMAND} -E echo "Windows coverage: use OpenCppCoverage or VS Enterprise CodeCoverage"
            COMMAND ${CMAKE_COMMAND} -E echo "Example: OpenCppCoverage.exe --modules tyche_tests.exe --export_type=html:coverage_report -- runtime\\win\\tyche_tests.exe"
            WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
            COMMENT "Coverage instructions for Windows..."
        )
    else()
        find_program(LCOV lcov)
        find_program(GENHTML genhtml)
        if(LCOV AND GENHTML)
            add_custom_target(coverage
                COMMAND ${LCOV} --capture --directory . --output-file coverage.info
                COMMAND ${LCOV} --remove coverage.info '/usr/*' '*/third_party/*' '*/tests/*' --output-file coverage.info
                COMMAND ${GENHTML} coverage.info --output-directory coverage_report
                WORKING_DIRECTORY ${CMAKE_BINARY_DIR}
                COMMENT "Generating coverage report..."
            )
        else()
            message(WARNING "lcov/genhtml not found; coverage target will not be available")
        endif()
    endif()
endif()
