use crate::enums::AssetClass;
use serde::{Deserialize, Serialize};

/// 64-bit packed instrument identifier.
/// Bit layout: [63..60] AssetClass (4) | [59..48] Venue (12) | [47..24] Symbol (24) | [23..0] Expiry/Strike (24)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct InstrumentId(u64);

impl InstrumentId {
    pub fn new(asset_class: AssetClass, venue: u16, symbol: u32, expiry_strike: u32) -> Self {
        let v = ((asset_class as u64) & 0xF) << 60
            | ((venue as u64) & 0xFFF) << 48
            | ((symbol as u64) & 0xFFFFFF) << 24
            | ((expiry_strike as u64) & 0xFFFFFF);
        Self(v)
    }

    pub fn from_raw(raw: u64) -> Self { Self(raw) }
    pub fn raw(&self) -> u64 { self.0 }

    pub fn asset_class(&self) -> Result<AssetClass, u8> {
        let bits = (self.0 >> 60) as u8;
        match bits {
            0 => Ok(AssetClass::Equity),
            1 => Ok(AssetClass::EquityOption),
            2 => Ok(AssetClass::Future),
            3 => Ok(AssetClass::FutureOption),
            4 => Ok(AssetClass::CryptoSpot),
            5 => Ok(AssetClass::CryptoPerp),
            6 => Ok(AssetClass::CryptoFuture),
            7 => Ok(AssetClass::FxSpot),
            8 => Ok(AssetClass::Bond),
            other => Err(other),
        }
    }

    pub fn venue(&self) -> u16 { ((self.0 >> 48) & 0xFFF) as u16 }
    pub fn symbol(&self) -> u32 { ((self.0 >> 24) & 0xFFFFFF) as u32 }
    pub fn expiry_strike(&self) -> u32 { (self.0 & 0xFFFFFF) as u32 }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::enums::AssetClass;

    #[test]
    fn encode_decode_roundtrip() {
        let id = InstrumentId::new(AssetClass::Equity, 1, 42, 0);
        assert_eq!(id.asset_class(), Ok(AssetClass::Equity));
        assert_eq!(id.venue(), 1);
        assert_eq!(id.symbol(), 42);
        assert_eq!(id.expiry_strike(), 0);
    }
    #[test]
    fn raw_value_is_deterministic() {
        let a = InstrumentId::new(AssetClass::CryptoSpot, 7, 100, 0);
        let b = InstrumentId::new(AssetClass::CryptoSpot, 7, 100, 0);
        assert_eq!(a.raw(), b.raw());
    }
    #[test]
    fn all_fields_max_values_fit() {
        let id = InstrumentId::new(AssetClass::Bond, 0xFFF, 0xFFFFFF, 0xFFFFFF);
        assert_eq!(id.venue(), 0xFFF);
        assert_eq!(id.symbol(), 0xFFFFFF);
        assert_eq!(id.expiry_strike(), 0xFFFFFF);
    }
    #[test]
    fn invalid_asset_class_bits_return_err() {
        // Manually craft an ID with asset_class bits = 15 (no enum variant)
        let raw: u64 = 0b1111u64 << 60;
        let id = InstrumentId::from_raw(raw);
        assert!(id.asset_class().is_err());
    }
}
