# C++单元测试覆盖率提升计划

## 目标
将项目C++代码单元测试覆盖率提升至80%以上。

## 现状分析
- **核心引擎**: 已有15个测试文件，覆盖基础组件，但缺少对引擎主逻辑、消息序列化高级场景、死信存储特殊字符等的测试。
- **CTP网关**: 已有7个测试文件，但缺少对配置解析、行情验证器、行情/交易SPI回调的完整测试。
- **覆盖率工具**: 项目未配置gcov/lcov，需先配置CMake以支持覆盖率报告生成。

## 实施步骤

### 1. 配置覆盖率工具链
- 修改 `CMakeLists.txt` 和 `tests/cpp/CMakeLists.txt`，添加gcov编译选项和覆盖率目标。
- 确保Windows下使用MinGW或WSL环境运行gcov，或配置OpenCppCoverage作为替代方案。

### 2. 核心引擎补充测试
- **消息序列化**: 补充测试空payload、极大payload、特殊字符（如JSON控制字符）的序列化与反序列化。
- **死信存储**: 测试并发写入、目录创建失败、文件权限异常等边界条件。
- **TopicQueue**: 测试所有背压策略（DROP_OLDEST, DROP_NEWEST, BLOCK_PRODUCER）的边界条件。
- **ShardedTopicMap**: 测试高并发读写、哈希冲突、桶扩容等场景。
- **引擎主循环**: 使用Mock ZMQ socket测试引擎的启动、停止、模块注册/注销流程。

### 3. CTP网关补充测试
- **配置解析**: 测试无效JSON、缺失必填字段、端口越界等异常输入。
- **QuoteValidator**: 补充测试价格跳变、时间戳回退、成交量异常等边界条件。
- **MdSpi/TdSpi**: 使用Mock CTP API测试连接、登录、订阅、行情推送、断开重连等完整流程。
- **CtpLoader**: 测试DLL路径验证、符号解析失败、TTS/CTP兼容模式切换。

### 4. 运行与验证
- 执行完整测试套件，收集覆盖率报告。
- 识别未覆盖代码区域，迭代补充测试用例直至覆盖率达到80%。
- 将覆盖率检查集成到CI流程（`.github/workflows/ci.yml`）。

## 关键文件路径
- `CMakeLists.txt`
- `tests/cpp/CMakeLists.txt`
- `tests/cpp/test_message.cpp`
- `tests/cpp/test_dead_letter_store.cpp`
- `tests/cpp/test_topic_queue.cpp`
- `tests/cpp/test_sharded_topic_map.cpp`
- `tests/cpp/test_engine.cpp` (新增)
- `tests/cpp/test_config.cpp` (新增)
- `tests/cpp/test_quote_validator.cpp` (新增)
- `tests/cpp/test_md_spi.cpp` (新增)
- `tests/cpp/test_td_spi.cpp` (新增)
- `tests/cpp/test_ctp_loader.cpp` (新增)
- `.github/workflows/ci.yml`
