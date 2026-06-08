# TycheEngine C++ 构建指南

本文档说明如何编译 TycheEngine 的 C++ 组件，包括核心引擎（`tyche_engine`）、模块静态库（`tyche_module`）和 CTP 网关（`ctp_gateway_cpp`）。

---

## 依赖要求

| 依赖 | 最低版本 | 说明 |
|------|---------|------|
| CMake | 3.16 | 构建系统 |
| C++ 编译器 | C++17 | MSVC (VS2022)、GCC 9+、Clang 10+ |
| Python | 3.9+ | 运行引擎和模块（C++ 组件为可选加速） |
| CTP SDK | - | **仅 CTP 网关需要**；行情/交易 API 头文件 |

> CTP SDK 头文件（`ThostFtdcMdApi.h`、`ThostFtdcTraderApi.h` 等）需要自行准备，详见下方 [CTP SDK 配置](#ctp-sdk-配置)。

---

## 快速开始（一键构建）

### Windows

```powershell
# Release 构建
.\build.bat

# Debug 构建
.\build.bat --debug

# 清理后重新构建
.\build.bat --clean
```

### Linux / macOS

```bash
# Release 构建
chmod +x build.sh
./build.sh

# Debug 构建
./build.sh --debug

# 清理后重新构建
./build.sh --clean
```

---

## 手动构建步骤

如果一键脚本不满足需求，可以手动执行 CMake：

### Windows（Visual Studio 2022）

```powershell
mkdir build
cd build
cmake .. -A x64 -DCMAKE_BUILD_TYPE=Release
cmake --build . --config Release
```

### Linux / macOS

```bash
mkdir -p build
cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
cmake --build . --parallel
```

---

## 编译产物位置

构建完成后，产物统一输出到 `build/` 目录下：

| 产物 | 路径（Windows） | 路径（Linux/macOS） |
|------|----------------|---------------------|
| 核心引擎 | `build/bin/Release/tyche_engine.exe` | `build/bin/tyche_engine` |
| 模块静态库 | `build/lib/Release/tyche_module.lib` | `build/lib/libtyche_module.a` |
| CTP 网关 | `build/bin/Release/ctp_gateway_cpp.exe` | `build/bin/ctp_gateway_cpp` |

> 使用 `--debug` 时，产物位于 `build/bin/Debug/`（Windows）或 `build/bin/`（Linux/macOS）。

---

## CTP SDK 配置

CTP 网关编译需要 CTP API 的头文件。提供两种方式：

### 方式一：复制到模块目录（推荐）

将 CTP SDK 中的头文件复制到：

```
src/modules/ctp_gateway_cpp/include/ctp/
  ThostFtdcMdApi.h
  ThostFtdcTraderApi.h
  ThostFtdcUserApiStruct.h
  ThostFtdcUserApiDataType.h
  ...（其他依赖头文件）
```

### 方式二：通过 CMake 参数指定

```powershell
cmake .. -DCTP_SDK_DIR="C:\openctp\include"
```

> 如果 CTP 头文件缺失，CMake 配置阶段会发出 **WARNING**，提示你补充头文件，而不会直接报错。编译 CTP 网关目标时才会失败。

---

## clangd / LSP 配置

构建脚本会自动将 `build/compile_commands.json` 复制到项目根目录。确保你的编辑器/LSP 客户端读取项目根目录的 `compile_commands.json`，即可获得准确的代码补全和跳转。

如果 `compile_commands.json` 未生成，检查：

1. 顶层 `CMakeLists.txt` 包含 `set(CMAKE_EXPORT_COMPILE_COMMANDS ON)`
2. 使用 Ninja 生成器时，`compile_commands.json` 直接生成在 build 根目录
3. 使用 Visual Studio 生成器时，可能需要切换到 Ninja 生成器以获得完整支持：
   ```powershell
   cmake .. -G Ninja -DCMAKE_BUILD_TYPE=Release
   ```

---

## 构建系统架构

```
TycheEngine/
├── CMakeLists.txt                 # 顶层入口：统一标准、产物目录、子项目
├── build.bat / build.sh           # 一键构建脚本
├── src/
│   ├── tyche/cpp/
│   │   ├── CMakeLists.txt         # 核心引擎 + 模块静态库
│   │   ├── engine/                # Engine 可执行文件源码
│   │   ├── module.cpp / module.h  # TycheModule C++ 实现
│   │   └── ...
│   └── modules/ctp_gateway_cpp/
│       ├── CMakeLists.txt         # CTP 网关可执行文件
│       ├── src/                   # 网关源码
│       └── include/ctp/           # CTP SDK 头文件（用户自行放置）
└── build/                         # 构建输出目录（自动生成）
    ├── bin/                       # 可执行文件
    ├── lib/                       # 静态/动态库
    └── compile_commands.json      # 编译数据库
```

---

## 常见问题

### Q: 编译时提示找不到 `zmq.hpp`

A: 项目依赖 `third_party/cppzmq` 和 `third_party/msgpack-c`，均为头文件库，已包含在仓库中。如果 `libzmq` 未安装，CMake 会自动从 `third_party/libzmq` 源码构建静态库。

### Q: CTP 网关编译失败，提示缺少 CTP 头文件

A: 按照 [CTP SDK 配置](#ctp-sdk-配置) 将头文件放入 `src/modules/ctp_gateway_cpp/include/ctp/`，或通过 `-DCTP_SDK_DIR=` 指定路径。

### Q: 如何只编译引擎，不编译 CTP 网关？

A: 可以注释掉顶层 `CMakeLists.txt` 中的 `add_subdirectory(src/modules/ctp_gateway_cpp)`，或仅构建指定目标：

```powershell
cmake --build . --config Release --target tyche_engine
```

### Q: 产物输出目录可以自定义吗？

A: 可以，在调用 CMake 时覆盖输出目录变量：

```powershell
cmake .. -DCMAKE_RUNTIME_OUTPUT_DIRECTORY=C:\tyche\bin -DCMAKE_ARCHIVE_OUTPUT_DIRECTORY=C:\tyche\lib
```
