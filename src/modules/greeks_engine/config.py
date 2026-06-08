"""Greeks Engine 配置."""

from dataclasses import dataclass, field
from typing import Dict, List, Set


@dataclass
class GreeksConfig:
    """Greeks Engine 模块配置.

    Attributes:
        risk_free_rate: 无风险利率 (年化)
        underlyings: 标的配置 — exchange_id -> list of product_ids
                     启动时自动从 static_data 查询期货和期权合约列表
        underlying_map: 期权合约 -> 标的合约映射 (自动从 static_data 构建)
        expiry_map: 期权合约 -> 到期日映射 (自动从 static_data 构建)
        underlying_instruments: 标的合约集合 (自动从 static_data 构建)
        engine_host: TycheEngine 主机地址
        engine_port: TycheEngine 注册端口
        resolve_timeout: 查询 static_data 超时时间 (秒)
    """

    risk_free_rate: float = 0.02
    # 标的配置: exchange_id -> [product_ids]
    underlyings: Dict[str, List[str]] = field(default_factory=dict)
    # 以下字段由引擎启动时从 static_data 自动构建
    # 期权合约 -> 标的合约映射
    underlying_map: Dict[str, str] = field(default_factory=dict)
    # 期权合约 -> 到期日映射
    expiry_map: Dict[str, str] = field(default_factory=dict)
    # 标的合约集合
    underlying_instruments: Set[str] = field(default_factory=set)
    engine_host: str = "127.0.0.1"
    engine_port: int = 5555
    resolve_timeout: float = 10.0
