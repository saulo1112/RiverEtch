// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.34;

/// @title Placeholder
/// @notice Minimal contract that exercises the Solidity toolchain: compile, lint, test and deploy.
/// @dev Scaffolding only. Delete it once the first real contract lands.
contract Placeholder {
    /// @notice The last value stored with `setValue`.
    uint256 public value;

    /// @notice Emitted when the stored value changes.
    /// @param previousValue The value before the update.
    /// @param newValue The value after the update.
    event ValueChanged(uint256 indexed previousValue, uint256 indexed newValue);

    /// @notice Thrown when the new value equals the stored one.
    /// @param value The value that is already stored.
    error ValueUnchanged(uint256 value);

    /// @notice Stores a new value.
    /// @param newValue The value to store; must differ from the current one.
    function setValue(uint256 newValue) external {
        uint256 previousValue = value;
        if (newValue == previousValue) revert ValueUnchanged(previousValue);
        value = newValue;
        emit ValueChanged(previousValue, newValue);
    }

    /// @notice Reports whether a non-zero value has been stored.
    /// @return isSet True when the stored value is not zero.
    function hasValue() external view returns (bool isSet) {
        isSet = value != 0;
    }
}
