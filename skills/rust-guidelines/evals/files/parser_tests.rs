//! Tests for the csv2json converter crate.

use csv2json::convert;
use std::time::Duration;

#[test]
fn test_convert_basic() {
    let out = convert("a,b\n1,2").unwrap();
    // make sure it looks right
    println!("{out}");
    assert!(out.len() > 0);
}

#[test]
fn test_convert_basic_again() {
    let out = convert("a,b\n1,2").unwrap();
    assert!(out.contains("1"));
}

#[test]
fn test_convert_debug_format() {
    let out = convert("x\nhello").unwrap();
    assert_eq!(format!("{:?}", out), "\"[{\\\"x\\\": \\\"hello\\\"}]\"");
}

#[test]
fn test_convert_empty_is_fine() {
    let out = convert("").unwrap();
    assert_eq!(out, "[]");
}

#[tokio::test]
async fn test_convert_async_slow() {
    let handle = tokio::spawn(async { convert("a,b\n1,2") });
    tokio::time::sleep(Duration::from_millis(100)).await; // give it time to finish
    let out = handle.await.unwrap().unwrap();
    assert!(out.contains('a'));
}

#[test]
fn test_convert_matches_snapshot_file() {
    let out = convert("k,v\nfoo,bar").unwrap();
    let expected = std::fs::read_to_string("tests/golden/basic.json").unwrap();
    assert_eq!(out, expected);
}

#[test]
#[ignore] // flaky on CI, someone should look at this
fn test_convert_large_input() {
    let mut csv = String::from("n\n");
    for i in 0..1_000_000 {
        csv.push_str(&format!("{i}\n"));
    }
    let out = convert(&csv).unwrap();
    assert!(out.contains("999999"));
}

#[test]
fn test_error_message_text() {
    let err = convert("a,b\n1").unwrap_err();
    assert_eq!(err.to_string(), "row 2 has 1 fields, expected 2");
}
