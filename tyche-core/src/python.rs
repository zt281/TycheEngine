use pyo3::prelude::*;
use pyo3::types::PyBytes;
use crate::{enums::*, types::*, ffi_bridge, serialization};

// ── PyQuote ──────────────────────────────────────────────────────────────────
#[pyclass]
#[derive(Clone)]
pub struct PyQuote { pub inner: Quote }

#[pymethods]
impl PyQuote {
    #[new]
    fn new(instrument_id: u64, bid_price: f64, bid_size: f64,
           ask_price: f64, ask_size: f64, timestamp_ns: u64) -> Self {
        Self { inner: Quote { instrument_id, bid_price, bid_size, ask_price, ask_size, timestamp_ns } }
    }
    #[getter] fn instrument_id(&self) -> u64 { self.inner.instrument_id }
    #[getter] fn bid_price(&self) -> f64 { self.inner.bid_price }
    #[getter] fn ask_price(&self) -> f64 { self.inner.ask_price }
    #[getter] fn bid_size(&self) -> f64 { self.inner.bid_size }
    #[getter] fn ask_size(&self) -> f64 { self.inner.ask_size }
    #[getter] fn timestamp_ns(&self) -> u64 { self.inner.timestamp_ns }
    fn spread(&self) -> f64 { self.inner.ask_price - self.inner.bid_price }
}

// ── PyTick ───────────────────────────────────────────────────────────────────
#[pyclass]
#[derive(Clone)]
pub struct PyTick { pub inner: Tick }

#[pymethods]
impl PyTick {
    #[new]
    fn new(instrument_id: u64, price: f64, size: f64, side: Side, seq: u64, timestamp_ns: u64) -> Self {
        Self { inner: Tick { instrument_id, price, size, side, _pad: [0;7], seq, timestamp_ns } }
    }
    #[getter] fn instrument_id(&self) -> u64 { self.inner.instrument_id }
    #[getter] fn price(&self) -> f64 { self.inner.price }
    #[getter] fn size(&self) -> f64 { self.inner.size }
    #[getter] fn side(&self) -> Side { self.inner.side }
    #[getter] fn seq(&self) -> u64 { self.inner.seq }
    #[getter] fn timestamp_ns(&self) -> u64 { self.inner.timestamp_ns }
}

// ── PyTrade ──────────────────────────────────────────────────────────────────
#[pyclass]
#[derive(Clone)]
pub struct PyTrade { pub inner: Trade }

#[pymethods]
impl PyTrade {
    #[new]
    fn new(instrument_id: u64, price: f64, size: f64, aggressor_side: Side, seq: u64, timestamp_ns: u64) -> Self {
        Self { inner: Trade { instrument_id, price, size, aggressor_side, _pad: [0;7], seq, timestamp_ns } }
    }
    #[getter] fn instrument_id(&self) -> u64 { self.inner.instrument_id }
    #[getter] fn price(&self) -> f64 { self.inner.price }
    #[getter] fn size(&self) -> f64 { self.inner.size }
    #[getter] fn aggressor_side(&self) -> Side { self.inner.aggressor_side }
    #[getter] fn seq(&self) -> u64 { self.inner.seq }
    #[getter] fn timestamp_ns(&self) -> u64 { self.inner.timestamp_ns }
}

// ── PyBar ────────────────────────────────────────────────────────────────────
#[pyclass]
#[derive(Clone)]
pub struct PyBar { pub inner: Bar }

#[pymethods]
impl PyBar {
    #[new]
    fn new(instrument_id: u64, open: f64, high: f64, low: f64, close: f64,
           volume: f64, interval: BarInterval, timestamp_ns: u64) -> Self {
        Self { inner: Bar { instrument_id, open, high, low, close, volume, interval, _pad: [0;7], timestamp_ns } }
    }
    #[getter] fn instrument_id(&self) -> u64 { self.inner.instrument_id }
    #[getter] fn open(&self) -> f64 { self.inner.open }
    #[getter] fn high(&self) -> f64 { self.inner.high }
    #[getter] fn low(&self) -> f64 { self.inner.low }
    #[getter] fn close(&self) -> f64 { self.inner.close }
    #[getter] fn volume(&self) -> f64 { self.inner.volume }
    #[getter] fn interval(&self) -> BarInterval { self.inner.interval }
    #[getter] fn timestamp_ns(&self) -> u64 { self.inner.timestamp_ns }
}

// ── PyOrder ───────────────────────────────────────────────────────────────────
#[pyclass]
#[derive(Clone)]
pub struct PyOrder { pub inner: Order }

#[pymethods]
impl PyOrder {
    #[new]
    fn new(instrument_id: u64, client_order_id: u64, price: f64, qty: f64,
           side: Side, order_type: OrderType, tif: TIF, timestamp_ns: u64) -> Self {
        Self { inner: Order { instrument_id, client_order_id, price, qty, side, order_type, tif, _pad: [0;5], timestamp_ns } }
    }
    #[getter] fn instrument_id(&self) -> u64 { self.inner.instrument_id }
    #[getter] fn client_order_id(&self) -> u64 { self.inner.client_order_id }
    #[getter] fn price(&self) -> f64 { self.inner.price }
    #[getter] fn qty(&self) -> f64 { self.inner.qty }
    #[getter] fn side(&self) -> Side { self.inner.side }
    #[getter] fn order_type(&self) -> OrderType { self.inner.order_type }
    #[getter] fn tif(&self) -> TIF { self.inner.tif }
    #[getter] fn timestamp_ns(&self) -> u64 { self.inner.timestamp_ns }
}

// ── PyOrderEvent ──────────────────────────────────────────────────────────────
#[pyclass]
#[derive(Clone)]
pub struct PyOrderEvent { pub inner: OrderEvent }

#[pymethods]
impl PyOrderEvent {
    #[new]
    fn new(instrument_id: u64, client_order_id: u64, exchange_order_id: u64,
           fill_price: f64, fill_qty: f64, kind: u8, timestamp_ns: u64) -> Self {
        let kind = match kind {
            0 => OrderEventKind::New, 1 => OrderEventKind::Cancel, 2 => OrderEventKind::Replace,
            3 => OrderEventKind::Fill, 4 => OrderEventKind::PartialFill, _ => OrderEventKind::Reject,
        };
        Self { inner: OrderEvent { instrument_id, client_order_id, exchange_order_id,
                                   fill_price, fill_qty, kind, _pad: [0;7], timestamp_ns } }
    }
    #[getter] fn instrument_id(&self) -> u64 { self.inner.instrument_id }
    #[getter] fn client_order_id(&self) -> u64 { self.inner.client_order_id }
    #[getter] fn exchange_order_id(&self) -> u64 { self.inner.exchange_order_id }
    #[getter] fn fill_price(&self) -> f64 { self.inner.fill_price }
    #[getter] fn fill_qty(&self) -> f64 { self.inner.fill_qty }
    #[getter] fn timestamp_ns(&self) -> u64 { self.inner.timestamp_ns }
}

// ── PyAck ────────────────────────────────────────────────────────────────────
#[pyclass]
#[derive(Clone)]
pub struct PyAck { pub inner: Ack }

#[pymethods]
impl PyAck {
    #[new]
    fn new(client_order_id: u64, exchange_order_id: u64, status: u8, sent_ns: u64, acked_ns: u64) -> Self {
        let status = match status { 1 => AckStatus::Rejected, 2 => AckStatus::CancelAcked, _ => AckStatus::Accepted };
        Self { inner: Ack { client_order_id, exchange_order_id, status, _pad: [0;7], sent_ns, acked_ns } }
    }
    #[getter] fn client_order_id(&self) -> u64 { self.inner.client_order_id }
    #[getter] fn exchange_order_id(&self) -> u64 { self.inner.exchange_order_id }
    #[getter] fn sent_ns(&self) -> u64 { self.inner.sent_ns }
    #[getter] fn acked_ns(&self) -> u64 { self.inner.acked_ns }
    #[getter] fn status(&self) -> u8 { self.inner.status as u8 }
}

// ── PyPosition ───────────────────────────────────────────────────────────────
#[pyclass]
#[derive(Clone)]
pub struct PyPosition { pub inner: Position }

#[pymethods]
impl PyPosition {
    #[new]
    fn new(instrument_id: u64, net_qty: f64, avg_cost: f64, timestamp_ns: u64) -> Self {
        Self { inner: Position { instrument_id, net_qty, avg_cost, timestamp_ns } }
    }
    #[getter] fn instrument_id(&self) -> u64 { self.inner.instrument_id }
    #[getter] fn net_qty(&self) -> f64 { self.inner.net_qty }
    #[getter] fn avg_cost(&self) -> f64 { self.inner.avg_cost }
    #[getter] fn timestamp_ns(&self) -> u64 { self.inner.timestamp_ns }
}

// ── PyRisk ───────────────────────────────────────────────────────────────────
#[pyclass]
#[derive(Clone)]
pub struct PyRisk { pub inner: Risk }

#[pymethods]
impl PyRisk {
    #[new]
    fn new(instrument_id: u64, delta: f64, gamma: f64, vega: f64, theta: f64,
           dv01: f64, notional: f64, margin: f64, timestamp_ns: u64) -> Self {
        Self { inner: Risk { instrument_id, delta, gamma, vega, theta, dv01, notional, margin, timestamp_ns } }
    }
    #[getter] fn instrument_id(&self) -> u64 { self.inner.instrument_id }
    #[getter] fn delta(&self) -> f64 { self.inner.delta }
    #[getter] fn gamma(&self) -> f64 { self.inner.gamma }
    #[getter] fn vega(&self) -> f64 { self.inner.vega }
    #[getter] fn theta(&self) -> f64 { self.inner.theta }
    #[getter] fn dv01(&self) -> f64 { self.inner.dv01 }
    #[getter] fn notional(&self) -> f64 { self.inner.notional }
    #[getter] fn margin(&self) -> f64 { self.inner.margin }
    #[getter] fn timestamp_ns(&self) -> u64 { self.inner.timestamp_ns }
}

// ── PyModel ──────────────────────────────────────────────────────────────────
#[pyclass]
#[derive(Clone)]
pub struct PyModel { pub inner: Model }

#[pymethods]
impl PyModel {
    #[new]
    fn new(version: u32, kind: ModelKind, valid_from_ns: u64, valid_to_ns: u64) -> Self {
        Self { inner: Model {
            version, kind, _pad: [0;3], valid_from_ns, valid_to_ns,
            param_keys: [0;16], param_vals: [0.0;16], param_count: 0, _pad2: [0;7]
        }}
    }
    #[getter] fn version(&self) -> u32 { self.inner.version }
    #[getter] fn kind(&self) -> ModelKind { self.inner.kind }
    #[getter] fn valid_from_ns(&self) -> u64 { self.inner.valid_from_ns }
    #[getter] fn valid_to_ns(&self) -> u64 { self.inner.valid_to_ns }
    #[getter] fn param_count(&self) -> u8 { self.inner.param_count }
}

// ── Module-level functions ────────────────────────────────────────────────────

#[pyfunction]
fn init_ffi_bridge(service_name: &str) {
    ffi_bridge::init_ffi_bridge(service_name);
}

#[pyfunction]
fn take_pending(service_name: &str, topic: &str, py: Python<'_>) -> Option<PyObject> {
    ffi_bridge::take_pending(service_name, topic)
        .map(|b| PyBytes::new_bound(py, &b).into())
}

#[pyfunction]
fn bar_interval_from_suffix(suffix: &str) -> PyResult<BarInterval> {
    BarInterval::from_suffix(suffix)
        .ok_or_else(|| pyo3::exceptions::PyValueError::new_err(
            format!("Unknown BarInterval suffix: '{suffix}'")))
}

// ── Serialize / deserialize helpers ──────────────────────────────────────────

macro_rules! serde_fns {
    ($ty:ty, $ser:ident, $de:ident, $py_ty:ident) => {
        #[pyfunction]
        fn $ser(val: &$py_ty, py: Python<'_>) -> PyResult<PyObject> {
            let bytes = serialization::serialize(&val.inner)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
            Ok(PyBytes::new_bound(py, &bytes).into())
        }
        #[pyfunction]
        fn $de(data: &[u8]) -> PyResult<$py_ty> {
            let inner: $ty = serialization::deserialize(data)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
            Ok($py_ty { inner })
        }
    };
}

serde_fns!(Quote,      serialize_quote,       deserialize_quote,       PyQuote);
serde_fns!(Tick,       serialize_tick,        deserialize_tick,        PyTick);
serde_fns!(Trade,      serialize_trade,       deserialize_trade,       PyTrade);
serde_fns!(Bar,        serialize_bar,         deserialize_bar,         PyBar);
serde_fns!(Order,      serialize_order,       deserialize_order,       PyOrder);
serde_fns!(OrderEvent, serialize_order_event, deserialize_order_event, PyOrderEvent);
serde_fns!(Ack,        serialize_ack,         deserialize_ack,         PyAck);
serde_fns!(Position,   serialize_position,    deserialize_position,    PyPosition);
serde_fns!(Risk,       serialize_risk,        deserialize_risk,        PyRisk);
serde_fns!(Model,      serialize_model,       deserialize_model,       PyModel);

// ── Module registration ───────────────────────────────────────────────────────

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Enums
    m.add_class::<BarInterval>()?;
    m.add_class::<ModelKind>()?;
    m.add_class::<Side>()?;
    m.add_class::<OrderType>()?;
    m.add_class::<TIF>()?;
    m.add_class::<AssetClass>()?;
    // Types
    m.add_class::<PyQuote>()?;
    m.add_class::<PyTick>()?;
    m.add_class::<PyTrade>()?;
    m.add_class::<PyBar>()?;
    m.add_class::<PyOrder>()?;
    m.add_class::<PyOrderEvent>()?;
    m.add_class::<PyAck>()?;
    m.add_class::<PyPosition>()?;
    m.add_class::<PyRisk>()?;
    m.add_class::<PyModel>()?;
    // FFI bridge
    m.add_function(wrap_pyfunction!(init_ffi_bridge, m)?)?;
    m.add_function(wrap_pyfunction!(take_pending, m)?)?;
    // BarInterval helper
    m.add_function(wrap_pyfunction!(bar_interval_from_suffix, m)?)?;
    // Serialize/deserialize pairs
    m.add_function(wrap_pyfunction!(serialize_quote, m)?)?;
    m.add_function(wrap_pyfunction!(deserialize_quote, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_tick, m)?)?;
    m.add_function(wrap_pyfunction!(deserialize_tick, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_trade, m)?)?;
    m.add_function(wrap_pyfunction!(deserialize_trade, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_bar, m)?)?;
    m.add_function(wrap_pyfunction!(deserialize_bar, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_order, m)?)?;
    m.add_function(wrap_pyfunction!(deserialize_order, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_order_event, m)?)?;
    m.add_function(wrap_pyfunction!(deserialize_order_event, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_ack, m)?)?;
    m.add_function(wrap_pyfunction!(deserialize_ack, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_position, m)?)?;
    m.add_function(wrap_pyfunction!(deserialize_position, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_risk, m)?)?;
    m.add_function(wrap_pyfunction!(deserialize_risk, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_model, m)?)?;
    m.add_function(wrap_pyfunction!(deserialize_model, m)?)?;
    Ok(())
}
