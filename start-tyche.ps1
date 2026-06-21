# TycheEngine 启动脚本 — 正确启动顺序
#
# 使用方式:
#   1. 先启动 TycheEngine (窗口1)
#   2. 再启动 static_data (窗口2)
#   3. 最后启动 CTP 网关 (窗口3)
#
# 注意: 所有模块必须先注册到 TycheEngine 才能互相通信。
#       static_data 不是独立服务，它只是 TycheEngine 的一个模块。

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("engine", "static_data", "ctp_gateway", "all")]
    [string]$Component = "all",

    [int]$RegistrationPort = 5555,
    [string]$Host = "127.0.0.1",
    [string]$DataDir = "data",
    [string]$ConfigFile = "runtime/gateway/simttsfut.json"
)

$ErrorActionPreference = "Stop"

function Start-Engine {
    Write-Host "[*] 启动 TycheEngine (注册端口: $RegistrationPort)..." -ForegroundColor Green
    Write-Host "    监听地址: $Host`:$RegistrationPort" -ForegroundColor Gray
    Write-Host "    按 Ctrl+C 停止" -ForegroundColor Gray
    python -m src.tyche.engine_main --registration-port $RegistrationPort --host $Host --data-dir $DataDir
}

function Start-StaticData {
    Write-Host "[*] 启动 static_data 模块..." -ForegroundColor Green
    Write-Host "    引擎地址: $Host`:$RegistrationPort" -ForegroundColor Gray
    Write-Host "    按 Ctrl+C 停止" -ForegroundColor Gray
    python -m src.modules.static_data --log-level INFO
}

function Start-CtpGateway {
    $gatewayDir = Split-Path -Parent $ConfigFile
    # 新目录结构：ctp_gateway_cpp.exe 在 runtime/win/gateway/ 下
    # 但配置文件仍在 runtime/gateway/ 下，需要找到正确的 exe 路径
    $exePath = Join-Path $gatewayDir "ctp_gateway_cpp.exe"
    
    # 如果不在配置文件同级目录，尝试从 engine/gateway 子目录查找
    if (-not (Test-Path $exePath)) {
        $exePath = Join-Path $gatewayDir "gateway\ctp_gateway_cpp.exe"
    }

    if (-not (Test-Path $exePath)) {
        Write-Error "CTP 网关可执行文件不存在: $exePath"
        Write-Host "    请确认已编译 ctp_gateway_cpp.exe 并放入 $gatewayDir 或其 gateway/ 子目录" -ForegroundColor Red
        exit 1
    }

    Write-Host "[*] 启动 CTP 网关..." -ForegroundColor Green
    Write-Host "    配置文件: $ConfigFile" -ForegroundColor Gray
    Write-Host "    按 Ctrl+C 停止" -ForegroundColor Gray

    Push-Location $gatewayDir
    try {
        # 根据 exe 路径决定工作目录
        $exeDir = Split-Path -Parent $exePath
        if ($exeDir -ne $gatewayDir) {
            Push-Location $exeDir
            try {
                .\ctp_gateway_cpp.exe --config (Join-Path $gatewayDir (Split-Path -Leaf $ConfigFile))
            } finally {
                Pop-Location
            }
        } else {
            .\ctp_gateway_cpp.exe --config (Split-Path -Leaf $ConfigFile)
        }
    } finally {
        Pop-Location
    }
}

function Show-Usage {
    Write-Host @"
TycheEngine 组件启动脚本

正确启动顺序（必须按此顺序，每个组件一个独立窗口）:

  窗口 1: 启动 TycheEngine 中心代理
   PS> .\start-tyche.ps1 -Component engine

  窗口 2: 启动 static_data 模块（提供合约查询服务）
   PS> .\start-tyche.ps1 -Component static_data

  窗口 3: 启动 CTP 网关
   PS> .\start-tyche.ps1 -Component ctp_gateway

或者使用 -Component all 在当前窗口依次启动（仅用于测试）:
   PS> .\start-tyche.ps1 -Component all

参数:
  -Component       要启动的组件: engine | static_data | ctp_gateway | all
  -RegistrationPort  注册端口 (默认: 5555)
  -Host            绑定地址 (默认: 127.0.0.1)
  -DataDir         数据目录 (默认: data)
  -ConfigFile      CTP 网关配置文件 (默认: runtime/gateway/simttsfut.json)

常见问题:
  Q: CTP 网关报告 "No handler for job 'query_instruments'"
  A: static_data 模块未启动或未成功注册到 TycheEngine。
     请确认: 1) TycheEngine 已启动 2) static_data 已启动且日志显示 "registered"

  Q: CTP 网关 Ctrl+C 无法退出
  A: 如果 static_data 未启动，网关会在 resolve_instruments 中阻塞等待。
     请确保按正确顺序启动所有组件。最新代码已修复此问题（异步解析合约）。

  Q: 端口被占用
  A: 检查是否有其他 TycheEngine 实例在运行:
     Get-NetTCPConnection -LocalPort 5555
"@ -ForegroundColor Cyan
}

# ── 主逻辑 ──────────────────────────────────────────────────────

if ($Component -eq "all") {
    Show-Usage
    Write-Host ""
    Write-Host "[!] 按 Enter 启动 TycheEngine，然后手动在新窗口启动其他组件..." -ForegroundColor Yellow
    Read-Host
    Start-Engine
} elseif ($Component -eq "engine") {
    Start-Engine
} elseif ($Component -eq "static_data") {
    Start-StaticData
} elseif ($Component -eq "ctp_gateway") {
    Start-CtpGateway
} else {
    Show-Usage
}
