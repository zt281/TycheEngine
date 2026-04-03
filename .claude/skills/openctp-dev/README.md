# openCTP Development Skill

Development guide for openCTP - an open-source CTPAPI-compatible interface for futures trading.

## Overview

openCTP provides CTPAPI-compatible interfaces for multiple trading channels:
- CTP (official China futures)
- XTP (Zhongtai Securities)
- TORA (Huaxin Securities)
- OST (Orient Securities)
- EMT (East Money Securities)
- TWS (Interactive Brokers)
- TAP (Esunny)
- QDP (Liangtou)

Plus a TTS-based simulation environment for 7x24 testing.

## Installation

### Python
```bash
pip install openctp-ctp==6.7.2.*  # Latest version
```

### C++
Download from [openctp.cn/download.html](http://www.openctp.cn/download.html)

## Quick Start

### Python - Market Data
```python
import openctp_ctp as ctp

class MdSpi(ctp.CThostFtdcMdSpi):
    def OnFrontConnected(self):
        req = ctp.CThostFtdcReqUserLoginField()
        req.BrokerID = b"9999"
        req.UserID = b"your_userid"
        req.Password = b"your_password"
        self._api.ReqUserLogin(req, 1)

    def OnRtnDepthMarketData(self, pDepthMarketData):
        print(f"{pDepthMarketData.InstrumentID}: {pDepthMarketData.LastPrice}")

# Create and connect
api = ctp.CThostFtdcMdApi.CreateFtdcMdApi()
spi = MdSpi()
spi._api = api
api.RegisterSpi(spi)
api.RegisterFront(b"tcp://180.168.146.187:10131")
api.Init()
```

### C++ - Trading
```cpp
#include "ThostFtdcTraderApi.h"

class TraderSpi : public CThostFtdcTraderSpi {
public:
    void OnFrontConnected() override {
        CThostFtdcReqUserLoginField req = {};
        strcpy(req.BrokerID, "9999");
        strcpy(req.UserID, "your_userid");
        strcpy(req.Password, "your_password");
        api->ReqUserLogin(&req, 1);
    }

    void OnRspUserLogin(CThostFtdcRspUserLoginField* pRspUserLogin,
                        CThostFtdcRspInfoField* pRspInfo,
                        int nRequestID, bool bIsLast) override {
        if (pRspInfo && pRspInfo->ErrorID == 0) {
            // Login success - save session info
            frontID = pRspUserLogin->FrontID;
            sessionID = pRspUserLogin->SessionID;
            maxOrderRef = atoi(pRspUserLogin->MaxOrderRef);
        }
    }

private:
    CThostFtdcTraderApi* api;
    int frontID, sessionID, maxOrderRef;
};
```

## Architecture

```
Python Layer → C++ Bridge (SWIG) → Native CTP Libraries → Exchange
     ↓
Callback Pattern (SPI)
```

## Core Classes

### Market Data
| Class | Purpose |
|-------|---------|
| `CThostFtdcMdApi` | Market data API interface |
| `CThostFtdcMdSpi` | Market data callbacks |

### Trading
| Class | Purpose |
|-------|---------|
| `CThostFtdcTraderApi` | Trading API interface |
| `CThostFtdcTraderSpi` | Trading callbacks |

## Connection Flow

1. **Create API** - `CreateFtdcTraderApi()` / `CreateFtdcMdApi()`
2. **Register SPI** - `RegisterSpi()` for callbacks
3. **Register Front** - `RegisterFront()` with server address
4. **Initialize** - `Init()` starts connection
5. **OnFrontConnected** callback triggered
6. **Login** - `ReqUserLogin()` with credentials
7. **OnRspUserLogin** callback - check `ErrorID == 0`
8. **Settlement Confirm** - `ReqSettlementInfoConfirm()` (trading only)
9. **Ready for operations**

## Error Handling

All responses include `CThostFtdcRspInfoField`:
```cpp
struct CThostFtdcRspInfoField {
    int ErrorID;        // 0 = success
    char ErrorMsg[81];  // Error description
};
```

Always check `ErrorID` before processing response data.

## Common Error Patterns

| Error Type | Callback Pattern | Handling |
|------------|------------------|----------|
| Sync Error | `OnRsp*` | Check `pRspInfo->ErrorID` |
| Async Error | `OnErrRtn*` | Handle operation failure |
| Network | `OnFrontDisconnected` | Reconnect logic |

## Key Data Structures

### Order Input
```cpp
struct CThostFtdcInputOrderField {
    char BrokerID[11];
    char InvestorID[13];
    char InstrumentID[31];
    char OrderRef[13];          // Unique order reference
    char Direction;             // '0'=Buy, '1'=Sell
    char CombOffsetFlag[5];     // '0'=Open, '1'=Close
    char CombHedgeFlag[5];      // '1'=Speculation
    double LimitPrice;
    int VolumeTotalOriginal;
    char TimeCondition;         // '1'=GFD, '3'=IOC
    char VolumeCondition;       // '1'=Any, '3'=All
    char MinVolume;
    char ContingentCondition;   // '1'=Immediately
    int RequestID;
};
```

### Order Response
```cpp
struct CThostFtdcOrderField {
    char BrokerID[11];
    char InvestorID[13];
    char InstrumentID[31];
    char OrderRef[13];
    char OrderSysID[21];        // Exchange order ID
    char OrderStatus;           // '0'=AllTraded, '1'=PartTraded, '3'=NoTrade, '5'=Canceled
    char StatusMsg[81];
    int FrontID;
    int SessionID;
};
```

## Order Reference Generation

After login, save these for order reference generation:
```cpp
frontID = pRspUserLogin->FrontID;
sessionID = pRspUserLogin->SessionID;
maxOrderRef = atoi(pRspUserLogin->MaxOrderRef);

// Generate unique order ref
sprintf(orderRef, "%d", ++maxOrderRef);
```

## Query Operations

| Query | API Function | Response Callback |
|-------|--------------|-------------------|
| Instruments | `ReqQryInstrument` | `OnRspQryInstrument` |
| Positions | `ReqQryInvestorPosition` | `OnRspQryInvestorPosition` |
| Orders | `ReqQryOrder` | `OnRspQryOrder` |
| Trades | `ReqQryTrade` | `OnRspQryTrade` |
| Account | `ReqQryTradingAccount` | `OnRspQryTradingAccount` |
| Commission | `ReqQryInstrumentCommissionRate` | `OnRspQryInstrumentCommissionRate` |
| Margin | `ReqQryInstrumentMarginRate` | `OnRspQryInstrumentMarginRate` |

## Best Practices

1. **Always check ErrorID** before processing response data
2. **Use RequestID** to correlate responses with requests
3. **Handle bIsLast** for multi-part query responses
4. **Confirm settlement** before trading
5. **Save session info** (FrontID, SessionID, MaxOrderRef) after login
6. **Generate unique OrderRef** using session info
7. **Thread safety**: API is not thread-safe, use from single thread
8. **Reconnection**: Handle `OnFrontDisconnected` with retry logic

## Testing Environment

Use TTS (Tick Trading System) for simulation:
```
Trade: tcp://121.37.80.177:20002
Market: tcp://121.37.80.177:20004
```

Or SimNow for CTP simulation (business hours only):
```
Trade: tcp://180.168.146.187:10130
Market: tcp://180.168.146.187:10131
```

## Platform Support

| Platform | C++ | Python |
|----------|-----|--------|
| Windows x86 | ✓ | ✓ |
| Windows x64 | ✓ | ✓ |
| Linux x64 | ✓ | ✓ |
| macOS x64 | ✓ | ✓ |
| macOS arm64 | ✓ | ✓ |

## Resources

- [openCTP GitHub](https://github.com/openctp/openctp)
- [Python API DeepWiki](https://deepwiki.com/openctp/openctp-ctp-python)
- [Download](http://www.openctp.cn/download.html)
