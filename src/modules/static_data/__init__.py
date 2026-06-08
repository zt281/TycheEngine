"""Static Data Module - 中国期货期权静态数据服务.

定期从 OpenCTP 数据中心获取交易所、品种、合约、报价、交易时段等静态数据，
持久化到本地文件，并通过 TycheEngine 的 Job 接口提供查询服务。
"""

from src.modules.static_data.config import StaticDataConfig
from src.modules.static_data.static_data import StaticDataModule

__all__ = ["StaticDataConfig", "StaticDataModule"]
