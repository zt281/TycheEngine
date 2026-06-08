#include "tyche/cpp/engine/engine.h"
#include "tyche/cpp/engine/shared_memory_bridge.h"

#include <nlohmann_json.hpp>

#include <atomic>
#include <csignal>
#include <cstring>
#include <fstream>
#include <iostream>
#include <string>

#ifdef _WIN32
#include <windows.h>
#endif

static std::atomic<bool> g_shutdown_requested{false};
static tyche::TycheEngine* g_engine = nullptr;

#ifdef _WIN32
BOOL WINAPI ConsoleCtrlHandler(DWORD ctrlType) {
    if (ctrlType == CTRL_C_EVENT || ctrlType == CTRL_CLOSE_EVENT) {
        g_shutdown_requested.store(true);
        if (g_engine) g_engine->stop();
        return TRUE;
    }
    return FALSE;
}
#else
void signal_handler(int sig) {
    (void)sig;
    g_shutdown_requested.store(true);
    if (g_engine) g_engine->stop();
}
#endif

// ── Configuration ───────────────────────────────────────────────────

struct Config {
    std::string host = "127.0.0.1";
    int port = 5555;
    std::string data_dir = "data";
    int queue_capacity = 10000;
    std::vector<tyche::ShmModuleConfig> shm_modules;
    std::vector<tyche::ShmBridgeConfig> shm_bridges;
};

static bool parse_json_config(const std::string& path, Config& cfg) {
    std::ifstream file(path);
    if (!file.is_open()) {
        std::cerr << "[TycheEngine] Error: cannot open config file: " << path << "\n";
        return false;
    }

    try {
        nlohmann::json j;
        file >> j;

        if (j.contains("host") && j["host"].is_string())
            cfg.host = j["host"].get<std::string>();
        if (j.contains("port") && j["port"].is_number())
            cfg.port = j["port"].get<int>();
        if (j.contains("data_dir") && j["data_dir"].is_string())
            cfg.data_dir = j["data_dir"].get<std::string>();
        if (j.contains("queue_capacity") && j["queue_capacity"].is_number())
            cfg.queue_capacity = j["queue_capacity"].get<int>();

        // Parse shared-memory modules
        if (j.contains("shm_modules") && j["shm_modules"].is_array()) {
            for (const auto& m : j["shm_modules"]) {
                tyche::ShmModuleConfig mc;
                if (m.contains("library_path") && m["library_path"].is_string())
                    mc.library_path = m["library_path"].get<std::string>();
                if (m.contains("shm_queue_name") && m["shm_queue_name"].is_string())
                    mc.shm_queue_name = m["shm_queue_name"].get<std::string>();
                if (m.contains("zmq_topics") && m["zmq_topics"].is_array()) {
                    for (const auto& t : m["zmq_topics"]) {
                        if (t.is_string()) mc.zmq_topics.push_back(t.get<std::string>());
                    }
                }
                if (!mc.library_path.empty() && !mc.shm_queue_name.empty()) {
                    cfg.shm_modules.push_back(std::move(mc));
                }
            }
        }

        // Parse shared-memory bridges
        if (j.contains("shm_bridges") && j["shm_bridges"].is_array()) {
            for (const auto& b : j["shm_bridges"]) {
                tyche::ShmBridgeConfig bc;
                if (b.contains("shm_queue_name") && b["shm_queue_name"].is_string())
                    bc.shm_queue_name = b["shm_queue_name"].get<std::string>();
                if (b.contains("zmq_topic") && b["zmq_topic"].is_string())
                    bc.zmq_topic = b["zmq_topic"].get<std::string>();
                if (!bc.shm_queue_name.empty() && !bc.zmq_topic.empty()) {
                    cfg.shm_bridges.push_back(std::move(bc));
                }
            }
        }
    } catch (const std::exception& e) {
        std::cerr << "[TycheEngine] Error parsing config file: " << e.what() << "\n";
        return false;
    }

    return true;
}

// ── Usage ───────────────────────────────────────────────────────────

static void print_usage(const char* prog) {
    std::cout << "Usage: " << prog << " [OPTIONS]\n"
              << "\n"
              << "Options:\n"
              << "  --host <addr>           Bind address (default: 127.0.0.1)\n"
              << "  --port <n>              Base port (default: 5555)\n"
              << "  --data-dir <path>       Data directory (default: data)\n"
              << "  --queue-capacity <n>    Queue capacity (default: 10000)\n"
              << "  --config <path>         JSON config file (optional)\n"
              << "  --help, -h              Show this help\n"
              << "\n"
              << "Port allocation (from base_port):\n"
              << "  Registration ROUTER:  base_port      (5555)\n"
              << "  Event XPUB:           base_port + 1  (5556)\n"
              << "  Event XSUB:           base_port + 2  (5557)\n"
              << "  Admin ROUTER:         base_port + 3  (5558)\n"
              << "  Heartbeat PUB:        base_port + 4  (5559)\n"
              << "  Heartbeat Recv:       base_port + 5  (5560)\n"
              << "  Job ROUTER:           base_port + 9  (5564)\n"
              << "\n"
              << "Config file fields:\n"
              << "  {\n"
              << "    \"host\": \"127.0.0.1\",\n"
              << "    \"port\": 5555,\n"
              << "    \"data_dir\": \"data\",\n"
              << "    \"queue_capacity\": 10000,\n"
              << "    \"shm_modules\": [\n"
              << "      {\n"
              << "        \"library_path\": \"modules/example.dll\",\n"
              << "        \"shm_queue_name\": \"tyche_shm_example\",\n"
              << "        \"zmq_topics\": [\"tick\", \"quote\"]\n"
              << "      }\n"
              << "    ],\n"
              << "    \"shm_bridges\": [\n"
              << "      {\n"
              << "        \"shm_queue_name\": \"tyche_shm_external\",\n"
              << "        \"zmq_topic\": \"market_data\"\n"
              << "      }\n"
              << "    ]\n"
              << "  }\n";
}

// ── Main ────────────────────────────────────────────────────────────

int main(int argc, char* argv[]) {
    Config cfg;
    std::string config_path;

    // First pass: check for --config to load defaults from file
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--config") == 0) {
            if (i + 1 >= argc) {
                std::cerr << "Error: --config requires a path argument\n";
                print_usage(argv[0]);
                return 1;
            }
            config_path = argv[++i];
        }
    }

    // Load JSON config if specified
    if (!config_path.empty()) {
        if (!parse_json_config(config_path, cfg)) {
            return 1;
        }
    }

    // Second pass: command-line arguments override config file
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--help") == 0 || std::strcmp(argv[i], "-h") == 0) {
            print_usage(argv[0]);
            return 0;
        } else if (std::strcmp(argv[i], "--host") == 0) {
            if (i + 1 >= argc) {
                std::cerr << "Error: --host requires an address argument\n";
                print_usage(argv[0]);
                return 1;
            }
            cfg.host = argv[++i];
        } else if (std::strcmp(argv[i], "--port") == 0) {
            if (i + 1 >= argc) {
                std::cerr << "Error: --port requires a number argument\n";
                print_usage(argv[0]);
                return 1;
            }
            try {
                cfg.port = std::stoi(argv[++i]);
            } catch (...) {
                std::cerr << "Error: invalid port number\n";
                print_usage(argv[0]);
                return 1;
            }
        } else if (std::strcmp(argv[i], "--data-dir") == 0) {
            if (i + 1 >= argc) {
                std::cerr << "Error: --data-dir requires a path argument\n";
                print_usage(argv[0]);
                return 1;
            }
            cfg.data_dir = argv[++i];
        } else if (std::strcmp(argv[i], "--queue-capacity") == 0) {
            if (i + 1 >= argc) {
                std::cerr << "Error: --queue-capacity requires a number argument\n";
                print_usage(argv[0]);
                return 1;
            }
            try {
                cfg.queue_capacity = std::stoi(argv[++i]);
            } catch (...) {
                std::cerr << "Error: invalid queue capacity\n";
                print_usage(argv[0]);
                return 1;
            }
        } else if (std::strcmp(argv[i], "--config") == 0) {
            // Already handled in first pass
            ++i;
        } else {
            std::cerr << "Error: unknown option: " << argv[i] << "\n";
            print_usage(argv[0]);
            return 1;
        }
    }

    // Compute endpoints from base port
    const int base_port = cfg.port;
    tyche::Endpoint registration_ep{cfg.host, base_port};
    tyche::Endpoint event_ep{cfg.host, base_port + 1};
    tyche::Endpoint heartbeat_ep{cfg.host, base_port + 4};
    tyche::Endpoint heartbeat_recv_ep{cfg.host, base_port + 5};
    tyche::Endpoint admin_ep{cfg.host, base_port + 3};
    tyche::Endpoint job_ep{cfg.host, base_port + 9};

    // Startup banner
    std::cout << "[TycheEngine] Starting C++ Engine v1.0\n"
              << "[TycheEngine] Registration: " << registration_ep.to_string() << "\n"
              << "[TycheEngine] Event PUB:    " << event_ep.to_string() << "\n"
              << "[TycheEngine] Heartbeat:    " << heartbeat_ep.to_string() << "\n"
              << "[TycheEngine] Admin:        " << admin_ep.to_string() << "\n"
              << "[TycheEngine] Job Router:   " << job_ep.to_string() << "\n"
              << "[TycheEngine] Data dir:     " << cfg.data_dir << "\n"
              << "[TycheEngine] Queue cap:    " << cfg.queue_capacity << "\n";

    if (!cfg.shm_modules.empty()) {
        std::cout << "[TycheEngine] SHM modules:  " << cfg.shm_modules.size() << "\n";
    }
    if (!cfg.shm_bridges.empty()) {
        std::cout << "[TycheEngine] SHM bridges:  " << cfg.shm_bridges.size() << "\n";
    }

    // Install signal handlers
#ifdef _WIN32
    SetConsoleCtrlHandler(ConsoleCtrlHandler, TRUE);
#else
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
#endif

    // Create and configure engine
    try {
        tyche::TycheEngine engine(
            registration_ep,
            event_ep,
            heartbeat_ep,
            heartbeat_recv_ep,
            admin_ep,
            job_ep,
            cfg.queue_capacity,
            cfg.data_dir);

        // Configure shared memory bridge before starting
        if (!cfg.shm_modules.empty() || !cfg.shm_bridges.empty()) {
            engine.shm_bridge()->configure(
                std::move(cfg.shm_modules),
                std::move(cfg.shm_bridges));
        }

        g_engine = &engine;

        std::cout << "[TycheEngine] Engine started. Press Ctrl+C to stop.\n";
        engine.run();

        g_engine = nullptr;
        std::cout << "[TycheEngine] Engine stopped.\n";
    } catch (const std::exception& ex) {
        std::cerr << "[TycheEngine] Fatal error: " << ex.what() << "\n";
        g_engine = nullptr;
        return 2;
    }

    return 0;
}
