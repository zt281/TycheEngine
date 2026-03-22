use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

pub trait Clock: Send + Sync {
    fn now_ns(&self) -> u64;
}

pub struct LiveClock;

impl Default for LiveClock {
    fn default() -> Self { Self }
}

impl LiveClock {
    pub fn new() -> Self { Self }
}

impl Clock for LiveClock {
    fn now_ns(&self) -> u64 {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system clock before Unix epoch")
            .as_nanos() as u64
    }
}

pub struct SimClock {
    current_ns: Arc<AtomicU64>,
}

impl SimClock {
    pub fn new(start_ns: u64) -> Self {
        Self { current_ns: Arc::new(AtomicU64::new(start_ns)) }
    }

    pub fn advance(&self, delta_ns: u64) {
        self.current_ns.fetch_add(delta_ns, Ordering::SeqCst);
    }
}

impl Clock for SimClock {
    fn now_ns(&self) -> u64 {
        self.current_ns.load(Ordering::SeqCst)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn live_clock_returns_positive_ns() {
        let c = LiveClock::new();
        assert!(c.now_ns() > 0);
    }

    #[test]
    fn live_clock_is_monotonic() {
        let c = LiveClock::new();
        let t1 = c.now_ns();
        let t2 = c.now_ns();
        assert!(t2 >= t1);
    }

    #[test]
    fn sim_clock_advance_increases_time() {
        let c = SimClock::new(0);
        c.advance(1_000_000);
        assert_eq!(c.now_ns(), 1_000_000);
    }
}
