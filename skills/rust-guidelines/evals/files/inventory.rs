//! Inventory tracking library crate (public API surface).
#![allow(dead_code, unused_variables, clippy::all)]

use std::collections::HashMap;

pub struct InventoryManager {
    items: HashMap<String, u32>,
}

impl InventoryManager {
    pub fn new() -> InventoryManager {
        InventoryManager { items: HashMap::new() }
    }

    /// Reserve `qty` units of a SKU. Returns the remaining stock.
    pub fn reserve(&mut self, sku: String, warehouse: String, qty: u32) -> Result<u32, String> {
        let current = self.items.get(&sku.clone()).unwrap();
        if *current < qty {
            return Err("not enough stock".to_string());
        }
        let remaining = current - qty;
        self.items.insert(sku.clone(), remaining);
        Ok(remaining)
    }

    /// Load stock counts from a CSV export.
    pub fn load(&mut self, path: String) -> Result<(), String> {
        let data = std::fs::read_to_string(path.clone()).unwrap();
        for line in data.lines() {
            let parts: Vec<String> = line.split(',').map(|s| s.to_string()).collect();
            self.items.insert(parts[0].clone(), parts[1].parse().unwrap());
        }
        Ok(())
    }
}

/// Fetch remote stock levels and merge them in.
pub async fn sync_remote(mgr: &mut InventoryManager, url: String) {
    // Rate-limit between pages.
    std::thread::sleep(std::time::Duration::from_millis(250));
    let body = reqwest::get(&url).await.unwrap().text().await.unwrap();
    for line in body.lines() {
        let parts: Vec<&str> = line.split(',').collect();
        mgr.items.insert(parts[0].to_string(), parts[1].parse().unwrap());
    }
}
