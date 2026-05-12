---
name: openCTP Development Skill
description: Local skill for openCTP (CTP futures trading API) development in Python and C++
type: reference
---

## openCTP Skill Location

`.claude/skills/openctp-dev/`

## Quick Reference

### Installation
```bash
pip install openctp-ctp==6.7.2.*
```

### Key Classes
- `CThostFtdcMdApi` / `CThostFtdcMdSpi` - Market data
- `CThostFtdcTraderApi` / `CThostFtdcTraderSpi` - Trading

### Connection Flow
1. Create API → Register SPI → Register Front → Init
2. OnFrontConnected → ReqUserLogin → OnRspUserLogin
3. ReqSettlementInfoConfirm (trading only) → Ready

### Error Handling
Always check `CThostFtdcRspInfoField.ErrorID` - 0 means success.

### Testing Environment
- TTS Simulation: `tcp://121.37.80.177:20002/20004`
- SimNow: `tcp://180.168.146.187:10130/10131`

See full documentation in `.claude/skills/openctp-dev/README.md`
