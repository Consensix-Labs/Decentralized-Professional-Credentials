// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title CredentialRegistry
/// @notice On-chain registry for anchoring W3C Verifiable Credential hashes.
///         Stores only hashes and metadata -- credential content stays off-chain
///         with the holder. Part of the Decentralized Professional Credentials PoC
///         by Consensix Labs.

contract CredentialRegistry {

    // --- Data Structures ---

    struct CredentialRecord {
        string issuer;          // did:key of the issuer
        uint64 issuedAt;        // block timestamp when registered
        uint64 expiration;      // 0 = no expiration, otherwise Unix timestamp (from validUntil)
        bool revoked;
        uint64 revokedAt;       // 0 until revoked
    }

    // --- Storage ---

    // Credential hash -> public record (accessible to verifiers)
    mapping(bytes32 => CredentialRecord) private records;

    // Credential hash -> registrant address (for revocation access control).
    // Separate from the public record because blockchain addresses are
    // chain-specific and shouldn't leak into the credential data model.
    mapping(bytes32 => address) private registrants;

    // --- Events ---

    event CredentialRegistered(
        bytes32 indexed credentialHash,
        string issuer,
        uint64 expiration,
        uint64 timestamp
    );

    event CredentialRevoked(
        bytes32 indexed credentialHash,
        uint64 timestamp
    );

    // --- Errors ---

    error CredentialAlreadyRegistered(bytes32 credentialHash);
    error CredentialNotFound(bytes32 credentialHash);
    error NotOriginalRegistrant(bytes32 credentialHash);
    error CredentialAlreadyRevoked(bytes32 credentialHash);
    error EmptyIssuer();

    // --- Public Functions ---

    /// @notice Anchor a credential hash on-chain.
    /// @param credentialHash SHA-256 hash of the signed JWT credential
    /// @param issuer The issuer's did:key identifier
    /// @param expiration Unix timestamp when the credential expires (0 for no expiration)
    function registerCredential(
        bytes32 credentialHash,
        string calldata issuer,
        uint64 expiration
    ) external {
        if (bytes(issuer).length == 0) {
            revert EmptyIssuer();
        }
        if (records[credentialHash].issuedAt != 0) {
            revert CredentialAlreadyRegistered(credentialHash);
        }

        uint64 now_ = uint64(block.timestamp);

        records[credentialHash] = CredentialRecord({
            issuer: issuer,
            issuedAt: now_,
            expiration: expiration,
            revoked: false,
            revokedAt: 0
        });

        registrants[credentialHash] = msg.sender;

        emit CredentialRegistered(credentialHash, issuer, expiration, now_);
    }

    /// @notice Revoke a previously registered credential. Only the original
    ///         registrant can revoke. Revocation is permanent.
    /// @param credentialHash SHA-256 hash of the credential to revoke
    function revokeCredential(bytes32 credentialHash) external {
        if (records[credentialHash].issuedAt == 0) {
            revert CredentialNotFound(credentialHash);
        }
        if (registrants[credentialHash] != msg.sender) {
            revert NotOriginalRegistrant(credentialHash);
        }
        if (records[credentialHash].revoked) {
            revert CredentialAlreadyRevoked(credentialHash);
        }

        uint64 now_ = uint64(block.timestamp);

        records[credentialHash].revoked = true;
        records[credentialHash].revokedAt = now_;

        emit CredentialRevoked(credentialHash, now_);
    }

    // --- View Functions ---

    /// @notice Get the full on-chain record for a credential.
    /// @param credentialHash SHA-256 hash of the credential
    /// @return exists Whether the credential is registered
    /// @return issuer The issuer's did:key
    /// @return issuedAt Block timestamp when registered
    /// @return expiration Expiration timestamp (0 = none)
    /// @return revoked Whether the credential has been revoked
    /// @return revokedAt Block timestamp when revoked (0 if not revoked)
    function getCredentialStatus(bytes32 credentialHash)
        external
        view
        returns (
            bool exists,
            string memory issuer,
            uint64 issuedAt,
            uint64 expiration,
            bool revoked,
            uint64 revokedAt
        )
    {
        CredentialRecord storage record = records[credentialHash];

        if (record.issuedAt == 0) {
            return (false, "", 0, 0, false, 0);
        }

        return (
            true,
            record.issuer,
            record.issuedAt,
            record.expiration,
            record.revoked,
            record.revokedAt
        );
    }

    /// @notice Check whether a credential is currently valid: registered,
    ///         not revoked, and not expired.
    /// @param credentialHash SHA-256 hash of the credential
    /// @return valid True only if the credential passes all three checks
    function isCredentialValid(bytes32 credentialHash)
        external
        view
        returns (bool valid)
    {
        CredentialRecord storage record = records[credentialHash];

        if (record.issuedAt == 0) {
            return false;
        }
        if (record.revoked) {
            return false;
        }
        if (record.expiration != 0 && record.expiration <= block.timestamp) {
            return false;
        }

        return true;
    }
}
