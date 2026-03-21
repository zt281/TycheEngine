pub mod clock;
pub mod enums;
pub mod ffi_bridge;
pub mod instrument;
pub mod serialization;
pub mod types;
mod python;

use pyo3::prelude::*;

#[pymodule]
fn tyche_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    python::register(m)
}
