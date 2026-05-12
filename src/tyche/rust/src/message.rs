//! MessagePack serialization for Tyche Engine messages.
//!
//! Compatible with Python's `msgpack` library (use_bin_type=True).

use crate::types::Message;

/// Serialize a Message to MessagePack bytes.
pub fn serialize_message(msg: &Message) -> Vec<u8> {
    rmp_serde::to_vec_named(msg).expect("Failed to serialize message")
}

/// Deserialize MessagePack bytes to a Message.
pub fn deserialize_message(data: &[u8]) -> Result<Message, rmp_serde::decode::Error> {
    rmp_serde::from_slice(data)
}
