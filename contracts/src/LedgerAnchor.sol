// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.34;

/// @title LedgerAnchor
/// @notice Public timestamps for TerraChain's append-only ledgers of sealed records.
/// @dev Each ledger line names the SHA-256 of the line before it, so the SHA-256 of its last line
/// (the head) commits to every record listed so far. Anchoring a head here proves that the ledger,
/// up to that line, existed at the block's time. A subject names one ledger, as
/// `keccak256("terrachain:<reach>:<ledger>")`.
contract LedgerAnchor {
    /// @notice One anchored state of a ledger.
    /// @param head The SHA-256 of the ledger's last line.
    /// @param lines The ledger's number of lines at that head.
    /// @param timestamp The block's timestamp.
    /// @param blockNumber The block's number.
    struct Anchor {
        bytes32 head;
        uint64 lines;
        uint64 timestamp;
        uint64 blockNumber;
    }

    /// @notice The only account allowed to anchor (the pipeline's operator), as `owner()`.
    address public immutable owner; // solhint-disable-line immutable-vars-naming

    mapping(bytes32 subject => Anchor[] anchors) private _anchors;

    /// @notice Emitted for every anchored head.
    /// @param subject The ledger.
    /// @param index The anchor's position in the ledger's history.
    /// @param head The SHA-256 of the ledger's last line.
    /// @param lines The ledger's number of lines.
    event Anchored(
        bytes32 indexed subject,
        uint256 indexed index,
        bytes32 head,
        uint64 indexed lines
    );

    /// @notice Thrown when someone other than the owner anchors.
    /// @param caller The account that tried.
    error NotOwner(address caller);

    /// @notice Thrown for an empty head or a ledger without lines.
    error EmptyAnchor();

    /// @notice Thrown when a ledger would shrink or repeat its last anchored head.
    /// @param lines The lines offered.
    /// @param previousLines The lines of the last anchor.
    error NotGrowing(uint64 lines, uint64 previousLines);

    /// @notice Thrown when the batch's arrays differ in length.
    error LengthMismatch();

    /// @notice Sets the deployer as the owner.
    constructor() {
        owner = msg.sender;
    }

    /// @notice Anchors one ledger's head.
    /// @param subject The ledger.
    /// @param head The SHA-256 of its last line.
    /// @param lines Its number of lines.
    function anchor(bytes32 subject, bytes32 head, uint64 lines) external {
        if (msg.sender != owner) revert NotOwner(msg.sender);
        _anchor(subject, head, lines);
    }

    /// @notice Anchors several ledgers' heads in one transaction.
    /// @param subjects The ledgers.
    /// @param heads The SHA-256 of each ledger's last line.
    /// @param lines Each ledger's number of lines.
    function anchorBatch(
        bytes32[] calldata subjects,
        bytes32[] calldata heads,
        uint64[] calldata lines
    ) external {
        if (msg.sender != owner) revert NotOwner(msg.sender);
        if (subjects.length != heads.length || subjects.length != lines.length) {
            revert LengthMismatch();
        }
        for (uint256 i = 0; i < subjects.length; ++i) {
            _anchor(subjects[i], heads[i], lines[i]);
        }
    }

    /// @notice How many times a ledger was anchored.
    /// @param subject The ledger.
    /// @return total The number of anchors.
    function count(bytes32 subject) external view returns (uint256 total) {
        total = _anchors[subject].length;
    }

    /// @notice One anchor of a ledger, oldest first.
    /// @param subject The ledger.
    /// @param index The anchor's position.
    /// @return anchored The anchor.
    function anchorAt(
        bytes32 subject,
        uint256 index
    ) external view returns (Anchor memory anchored) {
        anchored = _anchors[subject][index];
    }

    function _anchor(bytes32 subject, bytes32 head, uint64 lines) private {
        if (head == bytes32(0) || lines == 0) revert EmptyAnchor();
        Anchor[] storage list = _anchors[subject];
        uint256 n = list.length;
        if (n > 0) {
            Anchor storage last = list[n - 1];
            // A ledger only grows: the same head again, or fewer lines, is refused.
            if (!(lines > last.lines)) revert NotGrowing(lines, last.lines);
        }
        list.push(Anchor(head, lines, uint64(block.timestamp), uint64(block.number)));
        emit Anchored(subject, n, head, lines);
    }
}
