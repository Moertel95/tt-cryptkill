"""cocotb KAT + randomized test for the AES-128 core, checked against the
FIPS-197/IEEE-1619-verified golden model in ../model/aes_xts_ref.py."""
import os, sys, random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "model"))
from aes_xts_ref import aes_encrypt, aes_decrypt  # noqa: E402

async def run_block(dut, key: bytes, din: bytes, dec: int) -> bytes:
    dut.key.value = int.from_bytes(key, "big")
    dut.din.value = int.from_bytes(din, "big")
    dut.dec.value = dec
    await RisingEdge(dut.clk)
    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0
    for _ in range(64):
        await RisingEdge(dut.clk)
        if int(dut.done.value) == 1:
            got = int(dut.dout.value)
            return got.to_bytes(16, "big")
    raise AssertionError("timeout waiting for done")

@cocotb.test()
async def test_aes_kat(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rst_n.value = 0
    for _ in range(4):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    key = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
    pt  = bytes.fromhex("00112233445566778899aabbccddeeff")
    ct  = await run_block(dut, key, pt, 0)
    assert ct == bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a"), f"FIPS enc: {ct.hex()}"
    back = await run_block(dut, key, ct, 1)
    assert back == pt, f"FIPS dec: {back.hex()}"

    rnd = random.Random(0xC0FFEE)
    for i in range(32):
        k = bytes(rnd.randrange(256) for _ in range(16))
        p = bytes(rnd.randrange(256) for _ in range(16))
        c = await run_block(dut, k, p, 0)
        assert c == aes_encrypt(p, k), f"enc mismatch #{i}: {c.hex()} vs {aes_encrypt(p,k).hex()}"
        d = await run_block(dut, k, c, 1)
        assert d == p, f"dec mismatch #{i}: {d.hex()}"
    dut._log.info("AES-128 core: FIPS KAT + 32 random enc/dec vectors PASS")
