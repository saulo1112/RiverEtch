import assert from "node:assert/strict";
import { test } from "node:test";

import { truncateAddress, walletStatus } from "../src/features/wallet/state.ts";

const ADDRESS = "0x1234567890abcdef1234567890abcdef12345678";

void test("truncateAddress keeps the prefix, four digits and the last four", () => {
  assert.equal(truncateAddress(ADDRESS), "0x1234…5678");
});

void test("truncateAddress leaves short strings alone", () => {
  assert.equal(truncateAddress("0x12345678"), "0x12345678");
  assert.equal(truncateAddress(""), "");
});

void test("walletStatus waits for RainbowKit, then reads the account and the chain", () => {
  const account = { address: ADDRESS };
  assert.equal(walletStatus({ mounted: false, account, chain: {} }), "loading");
  assert.equal(walletStatus({ mounted: true }), "disconnected");
  assert.equal(walletStatus({ mounted: true, account }), "disconnected");
  assert.equal(
    walletStatus({ mounted: true, account, chain: { unsupported: true } }),
    "wrongNetwork",
  );
  assert.equal(
    walletStatus({ mounted: true, account, chain: { unsupported: false } }),
    "connected",
  );
  assert.equal(walletStatus({ mounted: true, account, chain: {} }), "connected");
});
