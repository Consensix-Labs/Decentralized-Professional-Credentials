/// On-chain registry for anchoring W3C Verifiable Credential hashes on IOTA.
///
/// This is the Move (IOTA Rebased) implementation of the same interface
/// provided by CredentialRegistry.sol on EVM. It uses a shared object
/// containing a Table for credential records (Option A), which is the
/// closest analog to Solidity's mapping pattern and enables a direct
/// comparison between the two chains.
///
/// The more idiomatic Move approach (Option B) would create individual
/// owned objects per credential. See the research paper for a discussion
/// of the tradeoffs.
module credential_registry::credential_registry {
    use std::string::String;
    use iota::table::{Self, Table};
    use iota::clock::Clock;
    use iota::event;

    // --- Error codes ---

    const ECredentialAlreadyRegistered: u64 = 0;
    const ECredentialNotFound: u64 = 1;
    const ENotOriginalRegistrant: u64 = 2;
    const ECredentialAlreadyRevoked: u64 = 3;
    const EEmptyIssuer: u64 = 4;

    // --- Data structures ---

    /// The shared registry object. Created once during module initialization
    /// and shared so that any address can register credentials.
    public struct Registry has key {
        id: UID,
        records: Table<vector<u8>, CredentialRecord>,
    }

    /// Individual credential record stored in the registry table.
    /// Keyed by the credential hash (SHA-256 of the signed JWT, as raw bytes).
    public struct CredentialRecord has store {
        issuer: String,             // did:key of the issuer
        registrant: address,        // address that registered (for revocation access control)
        issued_at: u64,             // timestamp in milliseconds when registered
        expiration: u64,            // 0 = no expiration, otherwise Unix timestamp in ms
        revoked: bool,
        revoked_at: u64,            // 0 until revoked
    }

    // --- Events ---

    public struct CredentialRegistered has copy, drop {
        credential_hash: vector<u8>,
        issuer: String,
        expiration: u64,
        timestamp: u64,
    }

    public struct CredentialRevoked has copy, drop {
        credential_hash: vector<u8>,
        timestamp: u64,
    }

    // --- Module initializer ---

    /// Creates the shared Registry object on package publish.
    /// This is called exactly once and makes the registry available
    /// to all users on the network.
    fun init(ctx: &mut TxContext) {
        transfer::share_object(Registry {
            id: object::new(ctx),
            records: table::new(ctx),
        });
    }

    // --- Public functions ---

    /// Anchor a credential hash on-chain.
    ///
    /// The credential_hash is the raw SHA-256 bytes (32 bytes) of the signed
    /// JWT. The issuer is their did:key string. Expiration is a Unix timestamp
    /// in milliseconds (0 for no expiration), matching IOTA's Clock resolution.
    public entry fun register_credential(
        registry: &mut Registry,
        credential_hash: vector<u8>,
        issuer: String,
        expiration: u64,
        clock: &Clock,
        ctx: &TxContext,
    ) {
        assert!(issuer.length() > 0, EEmptyIssuer);
        assert!(!table::contains(&registry.records, credential_hash), ECredentialAlreadyRegistered);

        let now = clock.timestamp_ms();

        // Copy hash and issuer for the event before moving into the table
        let hash_for_event = credential_hash;
        let issuer_for_event = issuer;

        table::add(&mut registry.records, credential_hash, CredentialRecord {
            issuer,
            registrant: ctx.sender(),
            issued_at: now,
            expiration,
            revoked: false,
            revoked_at: 0,
        });

        event::emit(CredentialRegistered {
            credential_hash: hash_for_event,
            issuer: issuer_for_event,
            expiration,
            timestamp: now,
        });
    }

    /// Revoke a previously registered credential. Only the original
    /// registrant can revoke. Revocation is permanent.
    public entry fun revoke_credential(
        registry: &mut Registry,
        credential_hash: vector<u8>,
        clock: &Clock,
        ctx: &TxContext,
    ) {
        assert!(table::contains(&registry.records, credential_hash), ECredentialNotFound);

        let record = table::borrow_mut(&mut registry.records, credential_hash);
        assert!(record.registrant == ctx.sender(), ENotOriginalRegistrant);
        assert!(!record.revoked, ECredentialAlreadyRevoked);

        let now = clock.timestamp_ms();
        record.revoked = true;
        record.revoked_at = now;

        event::emit(CredentialRevoked {
            credential_hash,
            timestamp: now,
        });
    }

    // --- View functions ---

    /// Check whether a credential hash exists in the registry.
    public fun credential_exists(
        registry: &Registry,
        credential_hash: vector<u8>,
    ): bool {
        table::contains(&registry.records, credential_hash)
    }

    /// Get the issuer DID for a registered credential.
    public fun get_issuer(
        registry: &Registry,
        credential_hash: vector<u8>,
    ): &String {
        assert!(table::contains(&registry.records, credential_hash), ECredentialNotFound);
        &table::borrow(&registry.records, credential_hash).issuer
    }

    /// Get the registration timestamp for a credential.
    public fun get_issued_at(
        registry: &Registry,
        credential_hash: vector<u8>,
    ): u64 {
        assert!(table::contains(&registry.records, credential_hash), ECredentialNotFound);
        table::borrow(&registry.records, credential_hash).issued_at
    }

    /// Get the expiration timestamp for a credential (0 = no expiration).
    public fun get_expiration(
        registry: &Registry,
        credential_hash: vector<u8>,
    ): u64 {
        assert!(table::contains(&registry.records, credential_hash), ECredentialNotFound);
        table::borrow(&registry.records, credential_hash).expiration
    }

    /// Check whether a credential has been revoked.
    public fun is_revoked(
        registry: &Registry,
        credential_hash: vector<u8>,
    ): bool {
        assert!(table::contains(&registry.records, credential_hash), ECredentialNotFound);
        table::borrow(&registry.records, credential_hash).revoked
    }

    /// Get the revocation timestamp (0 if not revoked).
    public fun get_revoked_at(
        registry: &Registry,
        credential_hash: vector<u8>,
    ): u64 {
        assert!(table::contains(&registry.records, credential_hash), ECredentialNotFound);
        table::borrow(&registry.records, credential_hash).revoked_at
    }

    /// Check whether a credential is currently valid: registered,
    /// not revoked, and not expired.
    public fun is_credential_valid(
        registry: &Registry,
        credential_hash: vector<u8>,
        clock: &Clock,
    ): bool {
        if (!table::contains(&registry.records, credential_hash)) {
            return false
        };

        let record = table::borrow(&registry.records, credential_hash);

        if (record.revoked) {
            return false
        };

        if (record.expiration != 0 && record.expiration <= clock.timestamp_ms()) {
            return false
        };

        true
    }

    // --- Test helpers ---

    #[test_only]
    public fun init_for_testing(ctx: &mut TxContext) {
        init(ctx);
    }
}
