"""Black-Scholes 核心定价模型 - 纯 Python 快速近似实现.

提供欧式期权定价、全量 Greeks 计算、Newton-Raphson 隐含波动率求解。
使用 Hastings 有理函数逼近实现标准正态分布 CDF 快速计算，
避免 Numba 依赖，同时保持足够精度（~1e-7）。
"""

import logging
import math

logger = logging.getLogger(__name__)


# ── 标准正态分布快速近似 ──────────────────────────────────────────
# Abramowitz & Stegun formula 26.2.17 (Hastings 有理函数逼近)
# 对 Q(x) = 1 - Φ(x) 的近似，绝对误差 < 7.5e-8
_AS_P = 0.2316419
_AS_B1 = 0.319381530
_AS_B2 = -0.356563782
_AS_B3 = 1.781477937
_AS_B4 = -1.821255978
_AS_B5 = 1.330274429
_SQRT_2PI = 2.5066282746310002  # math.sqrt(2.0 * math.pi)


def _norm_cdf(x):
    """标准正态分布累积分布函数 - A&S 26.2.17 快速近似.

    基于 Abramowitz & Stegun formula 26.2.17，绝对误差 < 7.5e-8。
    比 math.erfc 更快，纯 Python 实现无额外依赖。
    """
    # 利用对称性: Φ(-x) = 1 - Φ(x)，只对 x >= 0 计算
    ax = abs(x)

    t = 1.0 / (1.0 + _AS_P * ax)
    poly = t * (_AS_B1 + t * (_AS_B2 + t * (_AS_B3 + t * (_AS_B4 + t * _AS_B5))))
    q = poly * math.exp(-0.5 * ax * ax) / _SQRT_2PI  # Q(ax) = 1 - Φ(ax)

    if x >= 0:
        return 1.0 - q
    else:
        return q


def _norm_pdf(x):
    """标准正态分布概率密度函数."""
    return math.exp(-0.5 * x * x) / _SQRT_2PI


def bs_price(S, K, T, r, sigma, is_call):
    """Black-Scholes 欧式期权定价.

    Args:
        S: 标的价格
        K: 行权价
        T: 年化到期时间
        r: 无风险利率
        sigma: 波动率
        is_call: True=看涨, False=看跌

    Returns:
        期权理论价格
    """
    # 边界情况：到期时返回内在价值
    if T <= 0.0:
        intrinsic = max(S - K, 0.0) if is_call else max(K - S, 0.0)
        return intrinsic

    # 边界情况：波动率为零
    if sigma <= 0.0:
        df = math.exp(-r * T)
        if is_call:
            price = max(S - K * df, 0.0)
        else:
            price = max(K * df - S, 0.0)
        return price

    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T

    if is_call:
        price = S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    else:
        price = K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)
    return price


def bs_greeks(S, K, T, r, sigma, is_call):
    """计算全量 Greeks.

    Args:
        S: 标的价格
        K: 行权价
        T: 年化到期时间
        r: 无风险利率
        sigma: 波动率
        is_call: True=看涨, False=看跌

    Returns:
        (price, delta, gamma, vega, theta, rho) 元组
        - delta: 标的价格敏感度
        - gamma: delta 的变化率
        - vega: 波动率敏感度 (per 1% vol change)
        - theta: 时间衰减 (per day)
        - rho: 利率敏感度 (per 1% rate change)
    """
    # 边界情况：到期时
    if T <= 0.0:
        if is_call:
            intrinsic = max(S - K, 0.0)
            delta = 1.0 if S > K else 0.0
        else:
            intrinsic = max(K - S, 0.0)
            delta = -1.0 if S < K else 0.0
        return (intrinsic, delta, 0.0, 0.0, 0.0, 0.0)

    # 边界情况：波动率为零
    if sigma <= 0.0:
        df = math.exp(-r * T)
        if is_call:
            price = max(S - K * df, 0.0)
            delta = 1.0 if S > K * df else 0.0
        else:
            price = max(K * df - S, 0.0)
            delta = -1.0 if S < K * df else 0.0
        return (price, delta, 0.0, 0.0, 0.0, 0.0)

    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T

    nd1 = _norm_cdf(d1)
    nd2 = _norm_cdf(d2)
    n_neg_d1 = _norm_cdf(-d1)
    n_neg_d2 = _norm_cdf(-d2)
    pdf_d1 = _norm_pdf(d1)

    df = math.exp(-r * T)

    # Price
    if is_call:
        price = S * nd1 - K * df * nd2
    else:
        price = K * df * n_neg_d2 - S * n_neg_d1

    # Delta
    if is_call:
        delta = nd1
    else:
        delta = nd1 - 1.0

    # Gamma (same for call and put)
    gamma = pdf_d1 / (S * sigma * sqrt_T)

    # Vega (per 1% vol change, i.e. multiply by 0.01)
    vega = S * pdf_d1 * sqrt_T * 0.01

    # Theta (per day, i.e. divide by 365)
    if is_call:
        theta = (-(S * pdf_d1 * sigma) / (2.0 * sqrt_T)
                 - r * K * df * nd2) / 365.0
    else:
        theta = (-(S * pdf_d1 * sigma) / (2.0 * sqrt_T)
                 + r * K * df * n_neg_d2) / 365.0

    # Rho (per 1% rate change, i.e. multiply by 0.01)
    if is_call:
        rho = K * T * df * nd2 * 0.01
    else:
        rho = -K * T * df * n_neg_d2 * 0.01


    return (price, delta, gamma, vega, theta, rho)


def implied_vol(market_price, S, K, T, r, is_call, tol=1e-8, max_iter=100):
    """Newton-Raphson 隐含波动率求解.

    从市场价格反算隐含波动率。

    Args:
        market_price: 期权市场价格
        S: 标的价格
        K: 行权价
        T: 年化到期时间
        r: 无风险利率
        is_call: True=看涨, False=看跌
        tol: 收敛容差
        max_iter: 最大迭代次数

    Returns:
        隐含波动率 (float)，求解失败返回 -1.0
    """
    # 边界情况
    if T <= 0.0 or market_price <= 0.0:
        return -1.0

    # 初始猜测
    sigma = 0.3

    for i in range(max_iter):
        price = bs_price(S, K, T, r, sigma, is_call)
        diff = price - market_price

        if abs(diff) < tol:
            return sigma

        # 计算 vega (未缩放版本，用于 Newton-Raphson)
        sqrt_T = math.sqrt(T)
        d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrt_T)
        vega = S * _norm_pdf(d1) * sqrt_T

        # vega 为零时无法继续迭代
        if vega < 1e-12:
            return -1.0

        # Newton-Raphson 更新
        sigma = sigma - diff / vega

        # 保证 sigma 合理范围
        if sigma <= 0.0:
            sigma = 0.001
        if sigma > 10.0:
            return -1.0
    return -1.0
