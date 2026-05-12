//! Tyche Core - Shared types and base module implementation for Tyche Engine.
//!
//! This crate provides:
//! - Core types: Endpoint, ModuleId, Interface, Message, Payload
//! - Serialization: MessagePack encode/decode
//! - TycheModuleBase: Reusable ZeroMQ module foundation
//!
//! Future Rust modules should depend on this crate rather than
//! re-implementing the wire protocol and ZMQ lifecycle.

pub mod types;
pub mod message;
pub mod module;

pub use message::*;
pub use module::*;
pub use types::*;
