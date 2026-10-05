import { expect } from "chai";
import { network } from "hardhat";

const { ethers } = await network.create();

describe("Placeholder", function () {
  it("emits ValueChanged with the previous and the new value", async function () {
    const placeholder = await ethers.deployContract("Placeholder");

    await expect(placeholder.setValue(42n)).to.emit(placeholder, "ValueChanged").withArgs(0n, 42n);
    expect(await placeholder.value()).to.equal(42n);
    expect(await placeholder.hasValue()).to.equal(true);
  });

  it("reverts with ValueUnchanged when the value does not change", async function () {
    const placeholder = await ethers.deployContract("Placeholder");

    await expect(placeholder.setValue(0n))
      .to.be.revertedWithCustomError(placeholder, "ValueUnchanged")
      .withArgs(0n);
  });
});
