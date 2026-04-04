/// Unit tests for the credential registry contract.
///
/// These tests exercise the core operations: register, revoke, and query.
/// They use IOTA's test-only Clock utilities to control timestamps.
#[test_only]
#[allow(implicit_const_copy)]
module credential_registry::credential_registry_tests {
    use std::string;
    use iota::clock;
    use iota::test_scenario;
    use credential_registry::credential_registry;

    const TEST_ISSUER_DID: vector<u8> = b"did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK";
    const TEST_HASH: vector<u8> = x"ab2c87185f091b37eee47ba2fac300db746eb3aa827b77e60b67766ab9fa011c";

    #[test]
    fun test_register_and_query() {
        let issuer_addr = @0xA;
        let mut scenario = test_scenario::begin(issuer_addr);

        // Initialize the registry
        credential_registry::init_for_testing(scenario.ctx());
        scenario.next_tx(issuer_addr);

        // Get the shared registry object
        let mut registry = scenario.take_shared<credential_registry::Registry>();
        let mut test_clock = clock::create_for_testing(scenario.ctx());
        clock::set_for_testing(&mut test_clock, 1700000000000);

        // Register a credential
        credential_registry::register_credential(
            &mut registry,
            TEST_HASH,
            string::utf8(TEST_ISSUER_DID),
            0,
            &test_clock,
            scenario.ctx(),
        );

        // Verify it exists and has correct data
        assert!(credential_registry::credential_exists(&registry, TEST_HASH));
        assert!(*credential_registry::get_issuer(&registry, TEST_HASH) == string::utf8(TEST_ISSUER_DID));
        assert!(credential_registry::get_issued_at(&registry, TEST_HASH) == 1700000000000);
        assert!(credential_registry::get_expiration(&registry, TEST_HASH) == 0);
        assert!(!credential_registry::is_revoked(&registry, TEST_HASH));
        assert!(credential_registry::is_credential_valid(&registry, TEST_HASH, &test_clock));

        clock::destroy_for_testing(test_clock);
        test_scenario::return_shared(registry);
        scenario.end();
    }

    #[test]
    fun test_revoke() {
        let issuer_addr = @0xA;
        let mut scenario = test_scenario::begin(issuer_addr);

        credential_registry::init_for_testing(scenario.ctx());
        scenario.next_tx(issuer_addr);

        let mut registry = scenario.take_shared<credential_registry::Registry>();
        let mut test_clock = clock::create_for_testing(scenario.ctx());
        clock::set_for_testing(&mut test_clock, 1700000000000);

        credential_registry::register_credential(
            &mut registry,
            TEST_HASH,
            string::utf8(TEST_ISSUER_DID),
            0,
            &test_clock,
            scenario.ctx(),
        );

        clock::set_for_testing(&mut test_clock, 1700000006000);

        credential_registry::revoke_credential(
            &mut registry,
            TEST_HASH,
            &test_clock,
            scenario.ctx(),
        );

        assert!(credential_registry::is_revoked(&registry, TEST_HASH));
        assert!(credential_registry::get_revoked_at(&registry, TEST_HASH) == 1700000006000);
        assert!(!credential_registry::is_credential_valid(&registry, TEST_HASH, &test_clock));

        clock::destroy_for_testing(test_clock);
        test_scenario::return_shared(registry);
        scenario.end();
    }

    #[test]
    fun test_expiration() {
        let issuer_addr = @0xA;
        let mut scenario = test_scenario::begin(issuer_addr);

        credential_registry::init_for_testing(scenario.ctx());
        scenario.next_tx(issuer_addr);

        let mut registry = scenario.take_shared<credential_registry::Registry>();
        let mut test_clock = clock::create_for_testing(scenario.ctx());
        clock::set_for_testing(&mut test_clock, 1700000000000);

        // Register with expiration 10 seconds from now
        credential_registry::register_credential(
            &mut registry,
            TEST_HASH,
            string::utf8(TEST_ISSUER_DID),
            1700000010000,
            &test_clock,
            scenario.ctx(),
        );

        // Before expiration -- should be valid
        assert!(credential_registry::is_credential_valid(&registry, TEST_HASH, &test_clock));

        // After expiration -- should be invalid
        clock::set_for_testing(&mut test_clock, 1700000010001);
        assert!(!credential_registry::is_credential_valid(&registry, TEST_HASH, &test_clock));

        clock::destroy_for_testing(test_clock);
        test_scenario::return_shared(registry);
        scenario.end();
    }

    #[test]
    #[expected_failure(abort_code = credential_registry::ECredentialAlreadyRegistered)]
    fun test_double_registration_fails() {
        let issuer_addr = @0xA;
        let mut scenario = test_scenario::begin(issuer_addr);

        credential_registry::init_for_testing(scenario.ctx());
        scenario.next_tx(issuer_addr);

        let mut registry = scenario.take_shared<credential_registry::Registry>();
        let mut test_clock = clock::create_for_testing(scenario.ctx());
        clock::set_for_testing(&mut test_clock, 1700000000000);

        credential_registry::register_credential(
            &mut registry,
            TEST_HASH,
            string::utf8(TEST_ISSUER_DID),
            0,
            &test_clock,
            scenario.ctx(),
        );

        // Second registration with same hash should fail
        credential_registry::register_credential(
            &mut registry,
            TEST_HASH,
            string::utf8(TEST_ISSUER_DID),
            0,
            &test_clock,
            scenario.ctx(),
        );

        clock::destroy_for_testing(test_clock);
        test_scenario::return_shared(registry);
        scenario.end();
    }

    #[test]
    #[expected_failure(abort_code = credential_registry::ENotOriginalRegistrant)]
    fun test_revoke_by_non_registrant_fails() {
        let issuer_addr = @0xA;
        let other_addr = @0xB;
        let mut scenario = test_scenario::begin(issuer_addr);

        credential_registry::init_for_testing(scenario.ctx());
        scenario.next_tx(issuer_addr);

        let mut registry = scenario.take_shared<credential_registry::Registry>();
        let mut test_clock = clock::create_for_testing(scenario.ctx());
        clock::set_for_testing(&mut test_clock, 1700000000000);

        // Register as issuer_addr
        credential_registry::register_credential(
            &mut registry,
            TEST_HASH,
            string::utf8(TEST_ISSUER_DID),
            0,
            &test_clock,
            scenario.ctx(),
        );

        test_scenario::return_shared(registry);
        scenario.next_tx(other_addr);

        // Try to revoke as other_addr -- should fail
        let mut registry = scenario.take_shared<credential_registry::Registry>();
        credential_registry::revoke_credential(
            &mut registry,
            TEST_HASH,
            &test_clock,
            scenario.ctx(),
        );

        clock::destroy_for_testing(test_clock);
        test_scenario::return_shared(registry);
        scenario.end();
    }

    #[test]
    fun test_nonexistent_credential_not_valid() {
        let addr = @0xA;
        let mut scenario = test_scenario::begin(addr);

        credential_registry::init_for_testing(scenario.ctx());
        scenario.next_tx(addr);

        let registry = scenario.take_shared<credential_registry::Registry>();
        let test_clock = clock::create_for_testing(scenario.ctx());

        let fake_hash = x"0000000000000000000000000000000000000000000000000000000000000000";
        assert!(!credential_registry::credential_exists(&registry, fake_hash));
        assert!(!credential_registry::is_credential_valid(&registry, fake_hash, &test_clock));

        clock::destroy_for_testing(test_clock);
        test_scenario::return_shared(registry);
        scenario.end();
    }
}