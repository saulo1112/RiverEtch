// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.34;

import {Test} from "forge-std/Test.sol";
import {Placeholder} from "../../src/Placeholder.sol";

// Hardhat 3 runs Foundry-compatible Solidity tests: setUp() before each test_* / testFuzz_* function.
contract PlaceholderTest is Test {
    Placeholder internal placeholder;

    function setUp() public {
        placeholder = new Placeholder();
    }

    function test_InitialValueIsZero() public view {
        assertEq(placeholder.value(), 0);
        assertFalse(placeholder.hasValue());
    }

    function testFuzz_SetValue(uint256 newValue) public {
        vm.assume(newValue != 0);
        placeholder.setValue(newValue);
        assertEq(placeholder.value(), newValue);
        assertTrue(placeholder.hasValue());
    }

    function test_RevertWhen_ValueUnchanged() public {
        vm.expectRevert(abi.encodeWithSelector(Placeholder.ValueUnchanged.selector, 0));
        placeholder.setValue(0);
    }
}
