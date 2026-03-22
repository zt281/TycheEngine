use std::collections::HashMap;
use std::ptr;
use std::sync::atomic::{AtomicPtr, Ordering};
use std::sync::{OnceLock, RwLock};

/// Signal byte values sent over the inproc:// PAIR socket.
pub mod signal {
    pub const DATA_READY: u8 = 0x01;
    pub const SHUTDOWN: u8   = 0x02;
    pub const ERROR: u8      = 0x03;
}

// Global slot registry.
// Key: "{service_name}\0{topic}" (null-byte separator avoids collisions)
// Value: AtomicPtr to heap-allocated Vec<u8>; null = empty slot.
static SLOTS: OnceLock<RwLock<HashMap<String, AtomicPtr<Vec<u8>>>>> = OnceLock::new();

fn registry() -> &'static RwLock<HashMap<String, AtomicPtr<Vec<u8>>>> {
    SLOTS.get_or_init(|| RwLock::new(HashMap::new()))
}

fn slot_key(service_name: &str, topic: &str) -> String {
    format!("{service_name}\0{topic}")
}

/// Register a service. Currently a no-op (slots are created lazily on first write).
pub fn init_ffi_bridge(_service_name: &str) {}

/// Write payload into the per-topic slot; atomically replaces any un-taken value.
pub fn write_pending(service_name: &str, topic: &str, payload: Vec<u8>) {
    let key = slot_key(service_name, topic);
    let new_ptr = Box::into_raw(Box::new(payload));

    // Fast path: slot already registered — just swap
    {
        let map = registry().read().unwrap();
        if let Some(slot) = map.get(&key) {
            let old = slot.swap(new_ptr, Ordering::AcqRel);
            if !old.is_null() {
                unsafe { drop(Box::from_raw(old)); }
            }
            return;
        }
    }

    // Slow path: register new slot, then write
    let mut map = registry().write().unwrap();
    let slot = map.entry(key).or_insert_with(|| AtomicPtr::new(ptr::null_mut()));
    let old = slot.swap(new_ptr, Ordering::AcqRel);
    if !old.is_null() {
        unsafe { drop(Box::from_raw(old)); }
    }
}

/// Atomically take the pending payload; returns None if slot is empty.
pub fn take_pending(service_name: &str, topic: &str) -> Option<Vec<u8>> {
    let key = slot_key(service_name, topic);
    let map = registry().read().unwrap();
    let slot = map.get(&key)?;
    let ptr = slot.swap(ptr::null_mut(), Ordering::AcqRel);
    if ptr.is_null() {
        None
    } else {
        Some(unsafe { *Box::from_raw(ptr) })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn take_empty_slot_returns_none() {
        assert!(take_pending("svc_ta", "TOPIC_A").is_none());
    }
    #[test]
    fn write_then_take_returns_payload() {
        write_pending("svc_tb", "TOPIC_B", vec![1, 2, 3]);
        assert_eq!(take_pending("svc_tb", "TOPIC_B"), Some(vec![1, 2, 3]));
    }
    #[test]
    fn take_twice_second_is_none() {
        write_pending("svc_tc", "TOPIC_C", vec![1]);
        take_pending("svc_tc", "TOPIC_C");
        assert!(take_pending("svc_tc", "TOPIC_C").is_none());
    }
    #[test]
    fn write_overwrites_previous_slot() {
        write_pending("svc_td", "TOPIC_D", vec![1]);
        write_pending("svc_td", "TOPIC_D", vec![2, 3]);
        assert_eq!(take_pending("svc_td", "TOPIC_D"), Some(vec![2, 3]));
    }
}
