// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.34;

import {Test} from "forge-std/Test.sol";
import {LedgerAnchor} from "../../src/LedgerAnchor.sol";

contract LedgerAnchorTest is Test {
    LedgerAnchor internal anchors;
    bytes32 internal constant SUBJECT = keccak256("terrachain:platte-louisville:observations");
    bytes32 internal constant HEAD = keccak256("line 16");

    function setUp() public {
        anchors = new LedgerAnchor();
    }

    function test_TheDeployerOwnsIt() public view {
        assertEq(anchors.owner(), address(this));
    }

    function test_AnchorStoresTheHeadWithItsBlock() public {
        vm.warp(1_760_000_000);
        vm.roll(9_000_000);
        anchors.anchor(SUBJECT, HEAD, 16);
        assertEq(anchors.count(SUBJECT), 1);
        LedgerAnchor.Anchor memory a = anchors.anchorAt(SUBJECT, 0);
        assertEq(a.head, HEAD);
        assertEq(a.lines, 16);
        assertEq(a.timestamp, 1_760_000_000);
        assertEq(a.blockNumber, 9_000_000);
    }

    function test_RevertWhen_NotTheOwner() public {
        vm.prank(address(0xBEEF));
        vm.expectRevert(abi.encodeWithSelector(LedgerAnchor.NotOwner.selector, address(0xBEEF)));
        anchors.anchor(SUBJECT, HEAD, 16);
    }

    function test_RevertWhen_TheLedgerDoesNotGrow() public {
        anchors.anchor(SUBJECT, HEAD, 16);
        vm.expectRevert(abi.encodeWithSelector(LedgerAnchor.NotGrowing.selector, 16, 16));
        anchors.anchor(SUBJECT, keccak256("other"), 16);
        anchors.anchor(SUBJECT, keccak256("line 17"), 17);
        assertEq(anchors.count(SUBJECT), 2);
    }

    function test_RevertWhen_TheAnchorIsEmpty() public {
        vm.expectRevert(LedgerAnchor.EmptyAnchor.selector);
        anchors.anchor(SUBJECT, bytes32(0), 3);
        vm.expectRevert(LedgerAnchor.EmptyAnchor.selector);
        anchors.anchor(SUBJECT, HEAD, 0);
    }

    function test_ABatchAnchorsEveryLedger() public {
        bytes32[] memory subjects = new bytes32[](2);
        bytes32[] memory heads = new bytes32[](2);
        uint64[] memory lines = new uint64[](2);
        subjects[0] = SUBJECT;
        subjects[1] = keccak256("terrachain:platte-louisville:water-temperature");
        heads[0] = HEAD;
        heads[1] = keccak256("thermal line 16");
        lines[0] = 16;
        lines[1] = 16;
        anchors.anchorBatch(subjects, heads, lines);
        assertEq(anchors.count(subjects[0]), 1);
        assertEq(anchors.count(subjects[1]), 1);
    }

    function test_RevertWhen_TheBatchArraysDiffer() public {
        bytes32[] memory subjects = new bytes32[](2);
        bytes32[] memory heads = new bytes32[](1);
        uint64[] memory lines = new uint64[](2);
        vm.expectRevert(LedgerAnchor.LengthMismatch.selector);
        anchors.anchorBatch(subjects, heads, lines);
    }

    function testFuzz_AGrowingLedgerKeepsEveryAnchor(uint64 first, uint64 step) public {
        vm.assume(first > 0 && step > 0 && first < type(uint64).max - step);
        anchors.anchor(SUBJECT, HEAD, first);
        anchors.anchor(SUBJECT, keccak256("next"), first + step);
        assertEq(anchors.anchorAt(SUBJECT, 1).lines, first + step);
    }
}
