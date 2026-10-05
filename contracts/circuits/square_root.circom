pragma circom 2.2.0;

include "circomlib/circuits/comparators.circom";

// Toolchain demo only, not project logic: proves knowledge of a non-zero square root of a public
// value without revealing the root.
//
//   private input: root
//   public input:  square
template SquareRoot() {
    signal input root;
    signal input square;

    // Core relation: the prover knows `root` such that root * root == square (mod p).
    root * root === square;

    // Reject the trivial root 0. This also exercises the circomlib include path.
    signal rootIsZero <== IsZero()(root);
    rootIsZero === 0;
}

component main {public [square]} = SquareRoot();
