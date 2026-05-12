---
name: Binance Derivatives Gateway Skill
description: Local skill for Binance USD-M and COIN-M futures trading gateway development
type: reference
---

## Binance Derivatives Gateway Skill

`.claude/skills/binance-derivatives-gateway/`

## Quick Reference

### API Types
| Type | Base URL | Margined In |
|------|----------|-------------|
| USD-M | `https://fapi.binance.com` | USDT/BUSD |
| COIN-M | `https://dapi.binance.com` | BTC/ETH |

### Authentication
- HMAC SHA256 signature
- Headers: `X-MBX-APIKEY`
- Required params: `timestamp`, `recvWindow`, `signature`

### Key Endpoints
| Purpose | USD-M | COIN-M |
|---------|-------|--------|
| Account | `GET /fapi/v2/account` | `GET /dapi/v1/account` |
| Position | `GET /fapi/v2/positionRisk` | `GET /dapi/v1/positionRisk` |
| Place Order | `POST /fapi/v1/order` | `POST /dapi/v1/order` |
| Cancel Order | `DELETE /fapi/v1/order` | `DELETE /dapi/v1/order` |
| Order Book | `GET /fapi/v1/depth` | `GET /dapi/v1/depth` |

### Rate Limits
- 6000 request weight per minute
- Order placement: ~1200 orders/min

### WebSocket URLs
- USD-M: `wss://fstream.binance.com/ws/<stream>`
- COIN-M: `wss://dstream.binance.com/ws/<stream>`

See full documentation in `.claude/skills/binance-derivatives-gateway/README.md`
