//! Tests for field-level encryption.
#![cfg(feature = "encryption")]

use agit_core::encryption::StateEncryptor;
use agit_core::state::AgentState;
use serde_json::json;

#[test]
fn test_encrypt_decrypt_value() {
    let enc = StateEncryptor::new("test-key-123");
    let original = json!({"secret": "data", "count": 42});
    let encrypted = enc.encrypt_value(&original).unwrap();
    assert!(!encrypted.contains("secret")); // no plaintext leak
    let decrypted = enc.decrypt_value(&encrypted).unwrap();
    assert_eq!(original, decrypted);
}

#[test]
fn test_encrypt_decrypt_state() {
    let enc = StateEncryptor::new("my-secret-key");
    let state = AgentState::new(
        json!({"memory_key": "sensitive_data"}),
        json!({"world": "state_data"}),
    );
    let encrypted = enc.encrypt_state(&state).unwrap();
    // Encrypted fields should be ENC: prefixed strings
    assert!(encrypted.memory.is_string());
    assert!(encrypted.memory.as_str().unwrap().starts_with("ENC:"));
    assert!(encrypted.world_state.is_string());

    let decrypted = enc.decrypt_state(&encrypted).unwrap();
    assert_eq!(decrypted.memory, json!({"memory_key": "sensitive_data"}));
    assert_eq!(decrypted.world_state, json!({"world": "state_data"}));
}

#[test]
fn test_wrong_key_fails() {
    let enc1 = StateEncryptor::new("key-1");
    let enc2 = StateEncryptor::new("key-2");
    let original = json!({"secret": "data"});
    let encrypted = enc1.encrypt_value(&original).unwrap();
    assert!(enc2.decrypt_value(&encrypted).is_err());
}

#[test]
fn test_passthrough_unencrypted() {
    let enc = StateEncryptor::new("key");
    let state = AgentState::new(json!({"plain": "text"}), json!({}));
    // decrypt_state should pass through non-encrypted fields
    let result = enc.decrypt_state(&state).unwrap();
    assert_eq!(result.memory, json!({"plain": "text"}));
}

#[test]
fn test_empty_state() {
    let enc = StateEncryptor::new("key");
    let state = AgentState::new(json!({}), json!({}));
    let encrypted = enc.encrypt_state(&state).unwrap();
    let decrypted = enc.decrypt_state(&encrypted).unwrap();
    assert_eq!(decrypted.memory, json!({}));
    assert_eq!(decrypted.world_state, json!({}));
}

#[test]
fn test_large_state() {
    let enc = StateEncryptor::new("key");
    let mut large_obj = serde_json::Map::new();
    for i in 0..1000 {
        large_obj.insert(format!("key_{i}"), json!(format!("value_{i}")));
    }
    let state = AgentState::new(json!(large_obj), json!({}));
    let encrypted = enc.encrypt_state(&state).unwrap();
    let decrypted = enc.decrypt_state(&encrypted).unwrap();
    assert_eq!(decrypted.memory, state.memory);
}
