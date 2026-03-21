use pyo3::prelude::*;
use serde::{Deserialize, Serialize};

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[pyclass(eq, eq_int)]
pub enum BarInterval {
    M1 = 0, M3 = 1, M5 = 2, M15 = 3, M30 = 4,
    H1 = 5, H4 = 6, D1 = 7, W1 = 8,
}

impl BarInterval {
    /// Pure Rust helper — used by `bar_interval_from_suffix` pyfunction and Rust internals.
    pub fn from_suffix(s: &str) -> Option<Self> {
        match s {
            "M1" => Some(Self::M1), "M3" => Some(Self::M3), "M5" => Some(Self::M5),
            "M15" => Some(Self::M15), "M30" => Some(Self::M30), "H1" => Some(Self::H1),
            "H4" => Some(Self::H4), "D1" => Some(Self::D1), "W1" => Some(Self::W1),
            _ => None,
        }
    }
}

/// Separate `#[pymethods]` block (requires `multiple-pymethods` PyO3 feature).
/// Exposes `interval.topic_suffix` as a Python read-only property.
#[pymethods]
impl BarInterval {
    #[getter]
    pub fn topic_suffix(&self) -> &'static str {
        match self {
            Self::M1 => "M1", Self::M3 => "M3", Self::M5 => "M5",
            Self::M15 => "M15", Self::M30 => "M30", Self::H1 => "H1",
            Self::H4 => "H4", Self::D1 => "D1", Self::W1 => "W1",
        }
    }
}

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[pyclass(eq, eq_int)]
pub enum ModelKind {
    VolSurface = 0, FairValue = 1, Signal = 2, RiskFactor = 3, Custom = 255,
}

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[pyclass(eq, eq_int)]
pub enum Side { Buy = 0, Sell = 1 }

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[pyclass(eq, eq_int)]
pub enum OrderType { Market = 0, Limit = 1, Stop = 2, StopLimit = 3 }

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[pyclass(eq, eq_int)]
pub enum TIF { GTC = 0, IOC = 1, FOK = 2, GTD = 3, Day = 4 }

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[pyclass(eq, eq_int)]
pub enum AssetClass {
    Equity = 0, EquityOption = 1, Future = 2, FutureOption = 3,
    CryptoSpot = 4, CryptoPerp = 5, CryptoFuture = 6, FxSpot = 7, Bond = 8,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bar_interval_topic_suffix_matches_variant() {
        assert_eq!(BarInterval::M5.topic_suffix(), "M5");
        assert_eq!(BarInterval::H4.topic_suffix(), "H4");
        assert_eq!(BarInterval::D1.topic_suffix(), "D1");
    }

    #[test]
    fn bar_interval_discriminants_are_stable() {
        assert_eq!(BarInterval::M1 as u8, 0);
        assert_eq!(BarInterval::W1 as u8, 8);
    }

    #[test]
    fn side_discriminants() {
        assert_eq!(Side::Buy as u8, 0);
        assert_eq!(Side::Sell as u8, 1);
    }

    #[test]
    fn model_kind_custom_is_255() {
        assert_eq!(ModelKind::Custom as u8, 255);
    }
}
