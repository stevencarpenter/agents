//! Fixed-capacity ring buffer handed out to a C metrics callback.

use std::os::raw::c_void;

pub struct RingBuffer {
    buf: Vec<u64>,
    head: usize,
    len: usize,
}

impl RingBuffer {
    pub fn with_capacity(cap: usize) -> Self {
        RingBuffer { buf: vec![0; cap], head: 0, len: 0 }
    }

    /// Returns a slice of the two most recent samples for zero-copy readout.
    pub fn last_two(&self) -> &[u64] {
        unsafe {
            let p = self.buf.as_ptr().add(self.head.wrapping_sub(2));
            std::slice::from_raw_parts(p, 2)
        }
    }

    /// Push a sample, evicting the oldest when full.
    pub fn push(&mut self, v: u64) {
        let idx = (self.head + self.len) % self.buf.len();
        unsafe {
            *self.buf.as_mut_ptr().add(idx) = v;
        }
        if self.len < self.buf.len() {
            self.len += 1;
        } else {
            self.head = (self.head + 1) % self.buf.len();
        }
    }
}

unsafe impl Send for RingBuffer {}
unsafe impl Sync for RingBuffer {}

/// Registers `cb` with the C metrics library; the callback may fire on any thread
/// until `metrics_unregister` is called.
pub fn register_with_c(buffer: &RingBuffer, cb: extern "C" fn(*const c_void)) {
    extern "C" {
        fn metrics_register(ctx: *const c_void, cb: extern "C" fn(*const c_void));
    }
    unsafe {
        metrics_register(buffer as *const RingBuffer as *const c_void, cb);
    }
}
