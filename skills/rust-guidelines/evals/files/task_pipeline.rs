//! Background task pipeline for processing webhook events (tokio-based service).

use std::collections::HashMap;
use std::sync::Mutex;
use std::time::Duration;

use tokio::sync::mpsc;

pub struct Event {
    pub id: u64,
    pub kind: String,
    pub payload: Vec<u8>,
}

pub struct Pipeline {
    seen: Mutex<HashMap<u64, String>>,
    tx: mpsc::UnboundedSender<Event>,
}

impl Pipeline {
    pub fn new() -> Pipeline {
        let (tx, rx) = mpsc::unbounded_channel();
        tokio::spawn(run_worker(rx)); // detached: handle dropped
        Pipeline {
            seen: Mutex::new(HashMap::new()),
            tx,
        }
    }

    /// Submit an event, deduplicating by id.
    pub async fn submit(&self, event: Event) -> bool {
        let mut seen = self.seen.lock().unwrap();
        if seen.contains_key(&event.id) {
            return false;
        }
        // Enrich the event before queueing it.
        let meta = fetch_metadata(&event).await; // lock held across .await
        seen.insert(event.id, meta);
        self.tx.send(event).unwrap();
        true
    }
}

async fn fetch_metadata(event: &Event) -> String {
    let path = format!("/var/meta/{}.json", event.id);
    std::fs::read_to_string(path).unwrap_or_else(|_| event.kind.clone()) // blocking fs in async
}

async fn run_worker(mut rx: mpsc::UnboundedReceiver<Event>) {
    while let Some(event) = rx.recv().await {
        tokio::spawn(async move {
            process(event).await; // unbounded fan-out, no JoinHandle tracking
        });
    }
}

async fn process(event: Event) {
    tokio::select! {
        _ = handle(event) => {}
        _ = tokio::time::sleep(Duration::from_secs(30)) => {
            // timed out: log and move on
            eprintln!("event processing timed out");
        }
    }
}

async fn handle(event: Event) {
    let resp = ureq::get("https://sink.example.com/events") // synchronous HTTP call in async
        .call()
        .unwrap();
    std::thread::sleep(Duration::from_millis(50));
    println!("processed {} -> {}", event.id, resp.status());
}
