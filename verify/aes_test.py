"""cocotb KAT + randomized test for the AES-128 core, checked against the
FIPS-197/IEEE-1619-verified golden model in ../model/aes_xts_ref.py."""
import os, sys, random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

CYC = 400   # > byte-serial core latency (enc 248, dec 289 clk)

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
    for _ in range(CYC):
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


@cocotb.test()
async def test_aes_fsm_edges(dut):
    """Byte-serial FSM control: exact latency, inputs latched at start, start
    ignored while busy, held start = one op, start on the cycle after done."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.start.value = 0
    dut.rst_n.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    rnd = random.Random(7)
    rb = lambda: bytes(rnd.randrange(256) for _ in range(16))
    junk = lambda: int.from_bytes(rb(), "big")

    for dec in (0, 1):
        k, x = rb(), rb()
        want = aes_decrypt(x, k) if dec else aes_encrypt(x, k)
        dut.key.value, dut.din.value, dut.dec.value = int.from_bytes(k, "big"), int.from_bytes(x, "big"), dec
        dut.start.value = 1
        await RisingEdge(dut.clk)            # start sampled here
        dut.key.value, dut.din.value, dut.dec.value = junk(), junk(), 1 - dec   # must be ignored
        n = 0
        while True:
            await RisingEdge(dut.clk)
            n += 1
            if n == 5:
                dut.start.value = 0          # held 5 cycles: still one op
            if n == 50:
                dut.start.value = 1          # new edge while busy: ignored
            if n == 51:
                dut.start.value = 0
            if int(dut.done.value):
                break
            assert int(dut.busy.value) == 1, f"busy dropped early at {n}"
            assert n < CYC, "timeout"
        assert int(dut.busy.value) == 0
        assert int(dut.dout.value).to_bytes(16, "big") == want, f"dec={dec}"
        dut._log.info(f"dec={dec} latency {n} clk")
        assert n == (289 if dec else 248), n   # edges from start sample to done read high
        for _ in range(3):                   # dout holds after done
            await RisingEdge(dut.clk)
            assert int(dut.dout.value).to_bytes(16, "big") == want and not int(dut.done.value)

    # back-to-back: next start sampled on the edge right after done, alternating enc/dec
    k = rb()
    blocks = [rb() for _ in range(6)]
    for i, x in enumerate(blocks):
        dec = i & 1
        dut.key.value, dut.din.value, dut.dec.value = int.from_bytes(k, "big"), int.from_bytes(x, "big"), dec
        dut.start.value = 1
        await RisingEdge(dut.clk)
        dut.start.value = 0
        while not int(dut.done.value):
            await RisingEdge(dut.clk)
        want = aes_decrypt(x, k) if dec else aes_encrypt(x, k)
        assert int(dut.dout.value).to_bytes(16, "big") == want, f"b2b #{i}"
    # start held high across done (2.5 op lengths): exactly one op, no retrigger
    dut.start.value = 1
    ndone = 0
    for _ in range(750):
        await RisingEdge(dut.clk)
        ndone += int(dut.done.value)
    dut.start.value = 0
    assert ndone == 1 and int(dut.busy.value) == 0, f"held start ran {ndone} ops"
    dut._log.info("AES FSM edges PASS")
