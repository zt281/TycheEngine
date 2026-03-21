use serde::{Deserialize, Serialize};

pub fn serialize<T: Serialize>(val: &T) -> Result<Vec<u8>, rmp_serde::encode::Error> {
    rmp_serde::to_vec(val)
}

pub fn deserialize<T: for<'de> Deserialize<'de>>(data: &[u8]) -> Result<T, rmp_serde::decode::Error> {
    rmp_serde::from_slice(data)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::Quote;
    use crate::enums::*;

    #[test]
    fn quote_serialize_deserialize_roundtrip() {
        let q = Quote {
            instrument_id: 42,
            bid_price: 99.5,
            bid_size: 10.0,
            ask_price: 100.5,
            ask_size: 5.0,
            timestamp_ns: 1_000_000,
        };
        let bytes = serialize(&q).expect("serialize failed");
        let q2: Quote = deserialize(&bytes).expect("deserialize failed");
        assert_eq!(q2.instrument_id, 42);
        assert!((q2.bid_price - 99.5).abs() < 1e-9);
        assert!((q2.ask_price - 100.5).abs() < 1e-9);
    }
}
