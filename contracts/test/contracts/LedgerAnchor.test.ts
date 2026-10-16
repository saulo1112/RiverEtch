import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

import { expect } from "chai";
import { network } from "hardhat";

import { anchorLedgers, readAnchors } from "../../../web/src/features/chain/client.ts";
import { anchorStatus, ledgerHead, subjectLabel } from "../../../web/src/features/chain/ledger.ts";

const { ethers } = await network.create();

/**
 * The SHA-256 of a ledger line, as the pipeline and the web app compute it.
 *
 * @param line - The line, without its newline.
 * @returns The hash as a 0x-prefixed bytes32.
 */
function lineHash(line: string): string {
  return `0x${createHash("sha256").update(line, "utf8").digest("hex")}`;
}

describe("LedgerAnchor", function () {
  it("anchors a ledger's head and emits Anchored", async function () {
    const anchors = await ethers.deployContract("LedgerAnchor");
    const subject = ethers.id("terrachain:mississippi-belle-chasse:observations");
    const head = lineHash('{"recordSha256":"abc","previousLineSha256":null}');

    await expect(anchors.anchor(subject, head, 33n))
      .to.emit(anchors, "Anchored")
      .withArgs(subject, 0n, head, 33n);
    const stored = await anchors.anchorAt(subject, 0n);
    expect(stored.head).to.equal(head);
    expect(stored.lines).to.equal(33n);
  });

  it("refuses anyone but the owner", async function () {
    const other = (await ethers.getSigners())[1];
    if (other === undefined) {
      throw new Error("the test network needs two accounts");
    }
    const anchors = await ethers.deployContract("LedgerAnchor");
    const subject = ethers.id("terrachain:x:observations");

    await expect(anchors.connect(other).anchor(subject, lineHash("x"), 1n))
      .to.be.revertedWithCustomError(anchors, "NotOwner")
      .withArgs(await other.getAddress());
  });

  it("anchors a real reach ledger's head and gives it back to a reader", async function () {
    const file = new URL(
      "../../../docs/water-quality/reach/platte-louisville/examples/ledger.jsonl",
      import.meta.url,
    );
    const lines = readFileSync(file, "utf8")
      .split("\n")
      .filter((line) => line.trim() !== "");
    const head = lineHash(lines.at(-1) ?? "");
    const anchors = await ethers.deployContract("LedgerAnchor");
    const subject = ethers.id("terrachain:platte-louisville:observations");

    await anchors.anchor(subject, head, BigInt(lines.length));
    const stored = await anchors.anchorAt(subject, 0n);
    expect(stored.head).to.equal(head);
    expect(stored.lines).to.equal(BigInt(lines.length));
  });

  it("works with the web app's own client: anchor, read back, check a record", async function () {
    const text = readFileSync(
      new URL(
        "../../../docs/water-quality/reach/platte-louisville/examples/ledger.jsonl",
        import.meta.url,
      ),
      "utf8",
    );
    const { hashes, lines, head } = await ledgerHead(text);
    const anchors = await ethers.deployContract("LedgerAnchor");
    const address = await anchors.getAddress();
    const [owner] = await ethers.getSigners();
    if (owner === undefined || head === null) {
      throw new Error("no signer, or an empty ledger");
    }
    const label = subjectLabel("platte-louisville", "observations");

    // An earlier state (three records fewer), then the ledger as published.
    const earlier = lines - 3;
    await anchorLedgers(owner, address, [
      { label, head: hashes[earlier - 1] ?? "", lines: earlier },
    ]);
    await anchorLedgers(owner, address, [{ label, head, lines }]);
    const read = await readAnchors(owner, address, label);
    expect(read.map((a) => a.lines)).to.deep.equal([earlier, lines]);
    expect(anchorStatus(read, 0, hashes).state).to.equal("anchored"); // covered by the first
    expect(read[1]?.head).to.equal(head);
    // The last record is covered by the second anchor, whose head is the ledger's last line.
    const status = anchorStatus(read, lines - 1, hashes);
    expect(status.state).to.equal("anchored");
  });

  it("anchors every ledger of a batch in one transaction", async function () {
    const anchors = await ethers.deployContract("LedgerAnchor");
    const subjects = ["observations", "water-temperature"].map((l) =>
      ethers.id(`terrachain:platte-louisville:${l}`),
    );

    await anchors.anchorBatch(subjects, [lineHash("a"), lineHash("b")], [16n, 16n]);
    expect(await anchors.count(subjects[0] ?? "")).to.equal(1n);
    expect(await anchors.count(subjects[1] ?? "")).to.equal(1n);
  });
});
