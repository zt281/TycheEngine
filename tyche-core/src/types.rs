use crate::enums::*;
use serde::{Deserialize, Serialize};

#[repr(C)]
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct Tick {
    pub instrument_id: u64,
    pub price: f64,
    pub size: f64,
    pub side: Side,
    pub _pad: [u8; 7],
    pub seq: u64,
    pub timestamp_ns: u64,
}

#[repr(C)]
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct Quote {
    pub instrument_id: u64,
    pub bid_price: f64,
    pub bid_size: f64,
    pub ask_price: f64,
    pub ask_size: f64,
    pub timestamp_ns: u64,
}

#[repr(C)]
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct Trade {
    pub instrument_id: u64,
    pub price: f64,
    pub size: f64,
    pub aggressor_side: Side,
    pub _pad: [u8; 7],
    pub seq: u64,
    pub timestamp_ns: u64,
}

#[repr(C)]
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct Bar {
    pub instrument_id: u64,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
    pub interval: BarInterval,
    pub _pad: [u8; 7],
    pub timestamp_ns: u64,
}

#[repr(C)]
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct Order {
    pub instrument_id: u64,
    pub client_order_id: u64,
    pub price: f64,
    pub qty: f64,
    pub side: Side,
    pub order_type: OrderType,
    pub tif: TIF,
    pub _pad: [u8; 5],
    pub timestamp_ns: u64,
}

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum OrderEventKind {
    New = 0, Cancel = 1, Replace = 2, Fill = 3, PartialFill = 4, Reject = 5,
}

#[repr(C)]
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct OrderEvent {
    pub instrument_id: u64,
    pub client_order_id: u64,
    pub exchange_order_id: u64,
    pub fill_price: f64,
    pub fill_qty: f64,
    pub kind: OrderEventKind,
    pub _pad: [u8; 7],
    pub timestamp_ns: u64,
}

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AckStatus { Accepted = 0, Rejected = 1, CancelAcked = 2 }

#[repr(C)]
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct Ack {
    pub client_order_id: u64,
    pub exchange_order_id: u64,
    pub status: AckStatus,
    pub _pad: [u8; 7],
    pub sent_ns: u64,
    pub acked_ns: u64,
}

#[repr(C)]
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct Position {
    pub instrument_id: u64,
    pub net_qty: f64,
    pub avg_cost: f64,
    pub timestamp_ns: u64,
}

#[repr(C)]
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct Risk {
    pub instrument_id: u64,
    pub delta: f64,
    pub gamma: f64,
    pub vega: f64,
    pub theta: f64,
    pub dv01: f64,
    pub notional: f64,
    pub margin: f64,
    pub timestamp_ns: u64,
}

#[repr(C)]
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct Model {
    pub version: u32,
    pub kind: ModelKind,
    pub _pad: [u8; 3],
    pub valid_from_ns: u64,
    pub valid_to_ns: u64,
    pub param_keys: [u32; 16],
    pub param_vals: [f64; 16],
    pub param_count: u8,
    pub _pad2: [u8; 7],
}

pub type Timestamp = u64;

#[cfg(test)]
mod tests {
    use super::*;
    use crate::enums::*;

    #[test]
    fn tick_fields_accessible() {
        let t = Tick { instrument_id: 1, price: 100.0, size: 10.0,
                       side: Side::Buy, _pad: [0; 7], seq: 1, timestamp_ns: 0 };
        assert_eq!(t.price, 100.0);
    }
    #[test]
    fn quote_spread() {
        let q = Quote { instrument_id: 1, bid_price: 99.0, bid_size: 5.0,
                        ask_price: 100.0, ask_size: 3.0, timestamp_ns: 1000 };
        assert!(q.ask_price > q.bid_price);
    }
    #[test]
    fn bar_embeds_interval() {
        let b = Bar { instrument_id: 1, open: 100.0, high: 105.0, low: 99.0, close: 103.0,
                      volume: 1000.0, interval: BarInterval::M5, _pad: [0;7], timestamp_ns: 0 };
        assert_eq!(b.interval, BarInterval::M5);
    }
    #[test]
    fn order_side_and_type() {
        let o = Order { instrument_id: 1, client_order_id: 42, price: 100.0, qty: 10.0,
                        side: Side::Buy, order_type: OrderType::Limit, tif: TIF::GTC,
                        _pad: [0;5], timestamp_ns: 0 };
        assert_eq!(o.side, Side::Buy);
    }
    #[test]
    fn position_net_qty() {
        let p = Position { instrument_id: 1, net_qty: -100.0, avg_cost: 50.5, timestamp_ns: 0 };
        assert!(p.net_qty < 0.0);
    }
    #[test]
    fn model_param_capacity() {
        let m = Model { version: 1, kind: ModelKind::VolSurface, _pad: [0;3],
                        valid_from_ns: 0, valid_to_ns: u64::MAX,
                        param_keys: [0;16], param_vals: [0.0;16], param_count: 0, _pad2: [0;7] };
        assert_eq!(m.param_keys.len(), 16);
    }
}
