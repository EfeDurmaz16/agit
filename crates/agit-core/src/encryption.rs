//! Optional AES-256-GCM encryption for agent state at rest.
//!
//! Enable with `--features encryption`.
//! Provides `StateEncryptor` that encrypts/decrypts `AgentState` fields.

#[cfg(feature = "encryption")]
mod inner {
    use aes_gcm::{
        aead::{Aead, KeyInit, OsRng},
        Aes256Gcm, Nonce,
    };
    use aes_gcm::aead::generic_array::GenericArray;
    use aes_gcm::aead::rand_core::RngCore;
    use argon2::Argon2;
    use crate::error::{AgitError, Result};
    use crate::state::AgentState;
    use serde_json::Value;

    /// Fixed salt for deterministic key derivation from passphrase.
    /// In production, each tenant should have a unique salt stored alongside their config.
    const DEFAULT_SALT: &[u8; 16] = b"agit-enc-v1-salt";

    /// Encrypts and decrypts agent state fields using AES-256-GCM.
    /// Key derivation uses Argon2id (memory-hard KDF) for passphrase-based keys.
    pub struct StateEncryptor {
        cipher: Aes256Gcm,
    }

    impl StateEncryptor {
        /// Create a new encryptor from a passphrase/key string.
        /// The key is derived via Argon2id (memory-hard KDF) to resist brute-force attacks.
        pub fn new(key: &str) -> Self {
            Self::with_salt(key, DEFAULT_SALT)
        }

        /// Create from a passphrase with a custom salt.
        /// Each tenant should use a unique salt for key isolation.
        pub fn with_salt(key: &str, salt: &[u8]) -> Self {
            let mut key_bytes = [0u8; 32];
            Argon2::default()
                .hash_password_into(key.as_bytes(), salt, &mut key_bytes)
                .expect("Argon2 key derivation failed");
            let cipher = Aes256Gcm::new(GenericArray::from_slice(&key_bytes));
            Self { cipher }
        }

        /// Create from raw 32-byte key.
        pub fn from_key_bytes(key: &[u8; 32]) -> Self {
            let cipher = Aes256Gcm::new(GenericArray::from_slice(key));
            Self { cipher }
        }

        /// Encrypt a JSON value, returning a base64-encoded ciphertext string.
        pub fn encrypt_value(&self, value: &Value) -> Result<String> {
            let plaintext = serde_json::to_vec(value)
                .map_err(|e| AgitError::Serialization(e.to_string()))?;

            // Generate random 12-byte nonce
            let mut nonce_bytes = [0u8; 12];
            OsRng.fill_bytes(&mut nonce_bytes);
            let nonce = Nonce::from_slice(&nonce_bytes);

            let ciphertext = self.cipher.encrypt(nonce, plaintext.as_ref())
                .map_err(|e| AgitError::EncryptionError(format!("encrypt failed: {e}")))?;

            // Prepend nonce to ciphertext, then base64 encode
            let mut combined = Vec::with_capacity(12 + ciphertext.len());
            combined.extend_from_slice(&nonce_bytes);
            combined.extend_from_slice(&ciphertext);

            Ok(super::base64_encode(&combined))
        }

        /// Decrypt a base64-encoded ciphertext back to a JSON value.
        pub fn decrypt_value(&self, encrypted: &str) -> Result<Value> {
            let combined = super::base64_decode(encrypted)
                .map_err(|e| AgitError::EncryptionError(format!("base64 decode: {e}")))?;

            if combined.len() < 12 {
                return Err(AgitError::EncryptionError("ciphertext too short".into()));
            }

            let (nonce_bytes, ciphertext) = combined.split_at(12);
            let nonce = Nonce::from_slice(nonce_bytes);

            let plaintext = self.cipher.decrypt(nonce, ciphertext)
                .map_err(|e| AgitError::EncryptionError(format!("decrypt failed: {e}")))?;

            serde_json::from_slice(&plaintext)
                .map_err(|e| AgitError::Serialization(e.to_string()))
        }

        /// Encrypt an AgentState's memory and world_state fields in-place.
        /// Returns a new state with encrypted values wrapped as JSON strings.
        pub fn encrypt_state(&self, state: &AgentState) -> Result<AgentState> {
            let enc_memory = self.encrypt_value(&state.memory)?;
            let enc_world = self.encrypt_value(&state.world_state)?;

            Ok(AgentState {
                memory: Value::String(format!("ENC:{}", enc_memory)),
                world_state: Value::String(format!("ENC:{}", enc_world)),
                timestamp: state.timestamp,
                cost: state.cost,
                metadata: state.metadata.clone(),
            })
        }

        /// Decrypt an AgentState that was encrypted with encrypt_state.
        pub fn decrypt_state(&self, state: &AgentState) -> Result<AgentState> {
            let memory = self.decrypt_field(&state.memory)?;
            let world_state = self.decrypt_field(&state.world_state)?;

            Ok(AgentState {
                memory,
                world_state,
                timestamp: state.timestamp,
                cost: state.cost,
                metadata: state.metadata.clone(),
            })
        }

        fn decrypt_field(&self, value: &Value) -> Result<Value> {
            match value {
                Value::String(s) if s.starts_with("ENC:") => {
                    self.decrypt_value(&s[4..])
                }
                _ => Ok(value.clone()), // Not encrypted, pass through
            }
        }
    }
}

// Simple base64 encoding (no external dependency needed)
#[allow(dead_code)]
fn base64_encode(data: &[u8]) -> String {
    const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut result = String::with_capacity((data.len() + 2) / 3 * 4);
    for chunk in data.chunks(3) {
        let b0 = chunk[0] as u32;
        let b1 = if chunk.len() > 1 { chunk[1] as u32 } else { 0 };
        let b2 = if chunk.len() > 2 { chunk[2] as u32 } else { 0 };
        let n = (b0 << 16) | (b1 << 8) | b2;
        result.push(ALPHABET[((n >> 18) & 0x3F) as usize] as char);
        result.push(ALPHABET[((n >> 12) & 0x3F) as usize] as char);
        if chunk.len() > 1 {
            result.push(ALPHABET[((n >> 6) & 0x3F) as usize] as char);
        } else {
            result.push('=');
        }
        if chunk.len() > 2 {
            result.push(ALPHABET[(n & 0x3F) as usize] as char);
        } else {
            result.push('=');
        }
    }
    result
}

#[allow(dead_code)]
fn base64_decode(input: &str) -> std::result::Result<Vec<u8>, String> {
    let input = input.trim_end_matches('=');
    let mut result = Vec::with_capacity(input.len() * 3 / 4);
    let mut buf = 0u32;
    let mut bits = 0;
    for c in input.bytes() {
        let val = match c {
            b'A'..=b'Z' => c - b'A',
            b'a'..=b'z' => c - b'a' + 26,
            b'0'..=b'9' => c - b'0' + 52,
            b'+' => 62,
            b'/' => 63,
            _ => return Err(format!("invalid base64 char: {c}")),
        };
        buf = (buf << 6) | val as u32;
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            result.push((buf >> bits) as u8);
            buf &= (1 << bits) - 1;
        }
    }
    Ok(result)
}

#[cfg(feature = "encryption")]
pub use inner::StateEncryptor;
