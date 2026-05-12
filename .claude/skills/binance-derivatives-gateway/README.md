# Binance Derivatives Gateway Development Skill

Development guide for building trading gateways for Binance USD-M (Linear) and COIN-M (Inverse) futures markets.

## Overview

Binance operates two separate futures trading APIs:

| Type | Description | Base URL | API Path |
|------|-------------|----------|----------|
| **USD-M Futures** (Linear) | Stablecoin-margined (USDT/BUSD) | `https://fapi.binance.com` | `/fapi/v1/*`, `/fapi/v2/*` |
| **COIN-M Futures** (Inverse) | Crypto-margined (BTC/ETH) | `https://dapi.binance.com` | `/dapi/v1/*` |

## Quick Start

### Installation
```bash
pip install python-binance requests websockets
```

### Basic USD-M Client
```python
import hmac
import hashlib
import requests
import time
from typing import Dict, Optional

class BinanceUSDMCient:
    """Binance USD-M Futures API Client."""
    
    BASE_URL = "https://fapi.binance.com"
    
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = requests.Session()
    
    def _generate_signature(self, query_string: str) -> str:
        """Generate HMAC SHA256 signature."""
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def _signed_request(self, method: str, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Send signed request to API."""
        params = params or {}
        params['timestamp'] = int(time.time() * 1000)
        params['recvWindow'] = 5000
        
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        params['signature'] = self._generate_signature(query_string)
        
        url = f"{self.BASE_URL}{endpoint}"
        headers = {
            'X-MBX-APIKEY': self.api_key,
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        if method == 'GET':
            response = self.session.get(url, params=params, headers=headers)
        else:
            response = self.session.request(method, url, data=params, headers=headers)
        
        response.raise_for_status()
        return response.json()
    
    # Account endpoints
    def get_account(self) -> Dict:
        """Get account information and balances."""
        return self._signed_request('GET', '/fapi/v2/account')
    
    def get_positions(self) -> Dict:
        """Get position information."""
        return self._signed_request('GET', '/fapi/v2/positionRisk')
    
    # Order endpoints
    def place_order(self, symbol: str, side: str, order_type: str, 
                    quantity: float, **kwargs) -> Dict:
        """Place a new order.
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            side: 'BUY' or 'SELL'
            order_type: 'LIMIT', 'MARKET', 'STOP', etc.
            quantity: Order quantity
            **kwargs: Additional params (price, stopPrice, timeInForce, etc.)
        """
        params = {
            'symbol': symbol,
            'side': side,
            'type': order_type,
            'quantity': quantity,
            **kwargs
        }
        return self._signed_request('POST', '/fapi/v1/order', params)
    
    def cancel_order(self, symbol: str, order_id: int) -> Dict:
        """Cancel an order."""
        return self._signed_request('DELETE', '/fapi/v1/order', {
            'symbol': symbol,
            'orderId': order_id
        })
    
    def get_open_orders(self, symbol: Optional[str] = None) -> Dict:
        """Get open orders."""
        params = {'symbol': symbol} if symbol else {}
        return self._signed_request('GET', '/fapi/v1/openOrders', params)
    
    # Market data endpoints (no signature required)
    def get_orderbook(self, symbol: str, limit: int = 100) -> Dict:
        """Get order book."""
        url = f"{self.BASE_URL}/fapi/v1/depth"
        response = self.session.get(url, params={'symbol': symbol, 'limit': limit})
        response.raise_for_status()
        return response.json()
    
    def get_ticker(self, symbol: str) -> Dict:
        """Get latest price."""
        url = f"{self.BASE_URL}/fapi/v1/ticker/price"
        response = self.session.get(url, params={'symbol': symbol})
        response.raise_for_status()
        return response.json()
```

## Architecture

### Gateway Components

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Trading Engine │────▶│  BinanceGateway │────▶│  fapi.binance   │
│                 │     │                 │     │     .com        │
└─────────────────┘     │  ┌───────────┐  │     └─────────────────┘
                        │  │ Rate      │  │
                        │  │ Limiter   │  │     ┌─────────────────┐
                        │  └───────────┘  │────▶│ dapi.binance    │
                        │  ┌───────────┐  │     │    .com         │
                        │  │ WebSocket │  │     └─────────────────┘
                        │  │  Manager  │  │
                        │  └───────────┘  │
                        │  ┌───────────┐  │
                        │  │ Order     │  │
                        │  │  Manager  │  │
                        │  └───────────┘  │
                        └─────────────────┘
```

## Authentication

All trading endpoints require **HMAC SHA256 authentication**.

### Required Headers
```
X-MBX-APIKEY: <your_api_key>
Content-Type: application/x-www-form-urlencoded (for POST)
```

### Signature Generation
```python
def generate_signature(query_string: str, api_secret: str) -> str:
    """Generate HMAC SHA256 signature."""
    return hmac.new(
        api_secret.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

# Example usage
params = {
    'symbol': 'BTCUSDT',
    'side': 'BUY',
    'type': 'LIMIT',
    'quantity': 0.001,
    'price': 50000,
    'timeInForce': 'GTC',
    'timestamp': int(time.time() * 1000),
    'recvWindow': 5000
}

query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
signature = generate_signature(query_string, API_SECRET)
```

## Key Endpoints

### USD-M Futures (fapi.binance.com)

| Category | Endpoint | Method | Weight | Description |
|----------|----------|--------|--------|-------------|
| **Account** | `/fapi/v2/account` | GET | 10 | Account balance & positions |
| **Account** | `/fapi/v2/balance` | GET | 10 | Account balance only |
| **Position** | `/fapi/v2/positionRisk` | GET | 5 | Position risk/PNL |
| **Order** | `/fapi/v1/order` | POST | 1 | Place order |
| **Order** | `/fapi/v1/order` | DELETE | 1 | Cancel order |
| **Order** | `/fapi/v1/openOrders` | GET | 40 | Query open orders |
| **Order** | `/fapi/v1/allOrders` | GET | 20 | Query all orders |
| **Market** | `/fapi/v1/depth` | GET | 1-100 | Order book |
| **Market** | `/fapi/v1/ticker/price` | GET | 1 | Latest price |
| **Market** | `/fapi/v1/klines` | GET | 1-100 | Kline/candlestick data |
| **Trade** | `/fapi/v1/userTrades` | GET | 20 | Account trade list |
| **Funding** | `/fapi/v1/fundingRate` | GET | 1 | Funding rate history |
| **Leverage** | `/fapi/v1/leverage` | POST | 1 | Change leverage |
| **Margin** | `/fapi/v1/marginType` | POST | 1 | Change margin type |

### COIN-M Futures (dapi.binance.com)

| Category | Endpoint | Method | Weight | Description |
|----------|----------|--------|--------|-------------|
| **Account** | `/dapi/v1/account` | GET | 10 | Account info |
| **Position** | `/dapi/v1/positionRisk` | GET | 5 | Position risk |
| **Order** | `/dapi/v1/order` | POST | 1 | Place order |
| **Order** | `/dapi/v1/order` | DELETE | 1 | Cancel order |
| **Market** | `/dapi/v1/depth` | GET | 1-100 | Order book |
| **Market** | `/dapi/v1/ticker/price` | GET | 1 | Latest price |

## Rate Limits

### Request Weight Limits
- **Per Minute**: 6000 request weight per minute per API key
- **Per Second**: 1200 request weight per IP (for non-trading)

### Weight Examples
| Endpoint | Weight |
|----------|--------|
| Place order | 1 |
| Cancel order | 1 |
| Query open orders | 40 (all symbols) or 1 (single symbol) |
| Query account | 10 |
| Query position | 5 |
| Order book (limit 100) | 10 |
| Order book (limit 500) | 50 |
| Order book (limit 1000) | 100 |

### Order Rate Limits
- **Place Order**: 1200 orders per minute (under normal conditions)
- **Cancel Order**: 1200 cancels per minute
- **Batch Orders**: Max 5 orders per batch request

## WebSocket Streams

### Connection URLs
| Market | Stream URL |
|--------|------------|
| USD-M | `wss://fstream.binance.com/ws/<stream_name>` |
| COIN-M | `wss://dstream.binance.com/ws/<stream_name>` |
| Combined | `wss://fstream.binance.com/stream?streams=<stream1>/<stream2>` |

### Common Streams
```python
# Real-time streams
"<symbol>@aggTrade"          # Aggregate trade
"<symbol>@trade"             # Raw trade
"<symbol>@bookTicker"        # Best bid/ask
"<symbol>@markPrice"         # Mark price
"<symbol>@kline_<interval>"  # Kline (1m, 5m, 1h, etc.)
"<symbol>@depth<levels>"     # Order book (5, 10, 20 levels)

# User data stream (requires listenKey)
"<listenKey>"                # User data (orders, positions, balances)
```

### WebSocket Example
```python
import asyncio
import websockets
import json

async def subscribe_mark_price(symbol: str):
    """Subscribe to mark price stream."""
    uri = f"wss://fstream.binance.com/ws/{symbol.lower()}@markPrice"
    
    async with websockets.connect(uri) as ws:
        while True:
            msg = await ws.recv()
            data = json.loads(msg)
            print(f"Mark Price: {data['p']}, Funding Rate: {data['r']}")

# Run
asyncio.run(subscribe_mark_price("BTCUSDT"))
```

## Order Types

### USD-M Supported Types
| Type | Description |
|------|-------------|
| `LIMIT` | Limit order |
| `MARKET` | Market order |
| `STOP` | Stop-loss order |
| `STOP_MARKET` | Stop-loss market order |
| `TAKE_PROFIT` | Take-profit order |
| `TAKE_PROFIT_MARKET` | Take-profit market order |
| `TRAILING_STOP_MARKET` | Trailing stop market |

### Time in Force
| Value | Description |
|-------|-------------|
| `GTC` | Good Till Cancel (default) |
| `IOC` | Immediate or Cancel |
| `FOK` | Fill or Kill |
| `GTX` | Good Till Crossing (Post Only) |

## Best Practices

### 1. Rate Limit Management
```python
import time
from collections import deque

class RateLimiter:
    """Token bucket rate limiter for Binance API."""
    
    def __init__(self, max_weight: int = 6000, window: int = 60):
        self.max_weight = max_weight
        self.window = window
        self.requests = deque()
    
    def acquire(self, weight: int = 1):
        """Acquire permission to make request."""
        now = time.time()
        
        # Remove old requests outside window
        while self.requests and self.requests[0] < now - self.window:
            self.requests.popleft()
        
        # Check if we're over limit
        current_weight = sum(w for _, w in self.requests)
        if current_weight + weight > self.max_weight:
            sleep_time = self.requests[0] - (now - self.window)
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        self.requests.append((now, weight))
```

### 2. Error Handling
```python
from requests.exceptions import HTTPError, Timeout

class BinanceAPIError(Exception):
    pass

def handle_api_error(func):
    """Decorator for API error handling."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except HTTPError as e:
            error_data = e.response.json()
            code = error_data.get('code')
            msg = error_data.get('msg')
            
            if code == -2019:
                raise BinanceAPIError(f"Margin insufficient: {msg}")
            elif code == -2021:
                raise BinanceAPIError(f"Order would trigger immediately: {msg}")
            elif code == -1121:
                raise BinanceAPIError(f"Invalid symbol: {msg}")
            else:
                raise BinanceAPIError(f"API Error {code}: {msg}")
        except Timeout:
            raise BinanceAPIError("Request timeout")
    return wrapper
```

### 3. Timestamp Synchronization
```python
def sync_server_time(client):
    """Synchronize local time with server time."""
    response = requests.get("https://fapi.binance.com/fapi/v1/time")
    server_time = response.json()['serverTime']
    local_time = int(time.time() * 1000)
    client.time_offset = server_time - local_time
    return client.time_offset
```

### 4. Position Management
```python
class PositionManager:
    """Manage positions for multiple symbols."""
    
    def __init__(self, client):
        self.client = client
        self.positions = {}
    
    def update_positions(self):
        """Fetch and update all positions."""
        positions = self.client.get_positions()
        self.positions = {
            p['symbol']: {
                'size': float(p['positionAmt']),
                'entry': float(p['entryPrice']),
                'pnl': float(p['unRealizedProfit']),
                'leverage': int(p['leverage']),
                'margin_type': p['marginType']
            }
            for p in positions
            if float(p['positionAmt']) != 0
        }
        return self.positions
    
    def get_position(self, symbol: str) -> dict:
        """Get position for specific symbol."""
        return self.positions.get(symbol, {'size': 0})
    
    def is_hedged(self, symbol: str) -> bool:
        """Check if position is hedged."""
        # Check for both long and short positions
        positions = [p for p in self.positions.values() if p['symbol'] == symbol]
        return len(positions) > 1
```

## Testing

### Testnet Setup
```python
# Use testnet for development
TESTNET_URL = "https://testnet.binancefuture.com"

class BinanceTestnetClient(BinanceUSDMCient):
    BASE_URL = "https://testnet.binancefuture.com"
```

### Mock Testing
```python
import responses

@responses.activate
def test_place_order():
    """Test order placement with mocked response."""
    responses.add(
        responses.POST,
        'https://fapi.binance.com/fapi/v1/order',
        json={
            'orderId': 12345,
            'symbol': 'BTCUSDT',
            'status': 'NEW',
            'side': 'BUY',
            'price': '50000.00'
        },
        status=200
    )
    
    client = BinanceUSDMCient('test_key', 'test_secret')
    result = client.place_order('BTCUSDT', 'BUY', 'LIMIT', 0.001, price=50000)
    
    assert result['orderId'] == 12345
    assert result['status'] == 'NEW'
```

## Resources

- [Binance API Documentation](https://binance-docs.github.io/apidocs/futures/en/)
- [USD-M API Base](https://fapi.binance.com)
- [COIN-M API Base](https://dapi.binance.com)
- [Testnet](https://testnet.binancefuture.com)

## References

- [How to Connect Binance Futures to Python Trading](https://trading-strategies.academy/archives/1157)
- [Binance API HMAC SHA256 Authentication](https://binance-docs.github.io/apidocs/spot/en/#signed-trade-and-user_data-endpoint-security)
