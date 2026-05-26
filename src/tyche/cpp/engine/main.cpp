#include "tyche/cpp/engine/engine.h"

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

// ── Simple JSON config parser ────────────────────────────────────────

static std::string trim(const std::string& s) {
    size_t start = s.find_first_not_of(" \t\r\n");
    if (start == std::string::npos) return "";
    size_t end = s.find_last_not_of(" \t\r\n");
    return s.substr(start, end - start + 1);
}

static std::string strip_quotes(const std::string& s) {
    if (s.size() >= 2 && s.front() == '"' && s.back() == '"') {
        return s.substr(1, s.size() - 2);
    }
    return s;
}

struct Config {
    std::string host = "127.0.0.1";
    int port = 5555;
    std::string data_dir = "data";
    int queue_capacity = 10000;
};

static bool parse_json_config(const std::string& path, Config& cfg) {
    std::ifstream file(path);
    if (!file.is_open()) {
        std::cerr << "[TycheEngine] Error: cannot open config file: " << path << "\n";
        return false;
    }

    std::string line;
    while (std::getline(file, line)) {
        line = trim(line);
        // Skip braces, empty lines, comments
        if (line.empty() || line[0] == '{' || line[0] == '}' || line[0] == '/') {
            continue;
        }
        // Remove trailing comma
        if (!line.empty() && line.back() == ',') {
            line.pop_back();
        }

        size_t colon = line.find(':');
        if (colon == std::string::npos) continue;

        std::string key = trim(strip_quotes(trim(line.substr(0, colon))));
        std::string value = trim(line.substr(colon + 1));
        value = strip_quotes(value);

        if (key == "host") {
            cfg.host = value;
        } else if (key == "port") {
            cfg.port = std::stoi(value);
        } else if (key == "data_dir") {
            cfg.data_dir = value;
        } else if (key == "queue_capacity") {
            cfg.queue_capacity = std::stoi(value);
        }
    }
    return true;
}

// ── Usage ────────────────────────────────────────────────────────────

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
              << "  Job ROUTER:           base_port + 9  (5564)\n";
}

// ── Main ─────────────────────────────────────────────────────────────

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

    // Install signal handlers
#ifdef _WIN32
    SetConsoleCtrlHandler(ConsoleCtrlHandler, TRUE);
#else
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
#endif

    // Create and run engine
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
