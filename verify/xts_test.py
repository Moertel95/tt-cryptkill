"""cocotb test for the AES-128-XTS wrapper: IEEE-1619 vectors #1/#2 plus
randomized multi-block sectors (enc + dec), all checked against the golden
model ../model/aes_xts_ref.py::xts_crypt."""
import os, sys, random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "model"))
from aes_xts_ref import xts_crypt  # noqa: E402

async def pulse(dut, sig):
    sig.value = 1
    await RisingEdge(dut.clk)
    sig.value = 0
    await RisingEdge(dut.clk)

async def wait_idle(dut):
    for _ in range(64):
        if int(dut.busy.value) == 0:
            return
        await RisingEdge(dut.clk)
    raise AssertionError("timeout waiting for !busy")

async def run_sector(dut, data: bytes, key1: bytes, key2: bytes, seq: int, encrypt: bool) -> bytes:
    assert len(data) % 16 == 0
    dut.key1.value = int.from_bytes(key1, "big")
    dut.key2.value = int.from_bytes(key2, "big")
    dut.sector.value = seq
    await pulse(dut, dut.tweak_start)
    await wait_idle(dut)
    out = b""
    for j in range(0, len(data), 16):
        dut.din.value = int.from_bytes(data[j:j+16], "big")
        dut.dec.value = 0 if encrypt else 1
        dut.blk_start.value = 1
        await RisingEdge(dut.clk)
        dut.blk_start.value = 0
        for _ in range(64):
            await RisingEdge(dut.clk)
            if int(dut.done.value) == 1:
                break
        else:
            raise AssertionError(f"timeout on block {j//16}")
        await RisingEdge(dut.clk)   # dout must still be valid after done (held until next accept)
        out += int(dut.dout.value).to_bytes(16, "big")
    return out

async def reset(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rst_n.value = 0
    for _ in range(4):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

IEEE_VECTORS = [  # (key1, key2, seq, pt, ct) -- IEEE 1619-2007 XTS-AES-128 #1, #2
    ("00"*16, "00"*16, 0, "00"*32,
     "917cf69ebd68b2ec9b9fe9a3eadda692cd43d2f59598ed858c02c2652fbf922e"),
    ("11"*16, "22"*16, 0x3333333333, "44"*32,
     "c454185e6a16936e39334038acef838bfb186fff7480adc4289382ecd6d394f0"),
]

@cocotb.test()
async def test_xts_ieee1619(dut):
    await reset(dut)
    for n, (k1, k2, seq, pt, ct) in enumerate(IEEE_VECTORS, 1):
        k1, k2, pt, ct = map(bytes.fromhex, (k1, k2, pt, ct))
        got = await run_sector(dut, pt, k1, k2, seq, True)
        assert got == ct, f"IEEE vec#{n} enc: {got.hex()}"
        back = await run_sector(dut, ct, k1, k2, seq, False)
        assert back == pt, f"IEEE vec#{n} dec: {back.hex()}"
    dut._log.info("XTS: IEEE-1619 vectors #1/#2 enc+dec PASS")

@cocotb.test()
async def test_xts_random(dut):
    await reset(dut)
    rnd = random.Random(0x1619)
    for i in range(12):
        k1 = bytes(rnd.randrange(256) for _ in range(16))
        k2 = bytes(rnd.randrange(256) for _ in range(16))
        # full 128-bit range exercises the LE byte swap; also hit small sectors
        seq = rnd.getrandbits(128) if i % 2 else rnd.getrandbits(32)
        nblk = 32 if i == 0 else rnd.randrange(1, 17)   # one full 512-byte sector
        pt = bytes(rnd.randrange(256) for _ in range(16 * nblk))
        exp = xts_crypt(pt, k1, k2, seq, encrypt=True)
        ct = await run_sector(dut, pt, k1, k2, seq, True)
        assert ct == exp, f"rand #{i} enc ({nblk} blk): {ct.hex()} vs {exp.hex()}"
        back = await run_sector(dut, ct, k1, k2, seq, False)
        assert back == pt, f"rand #{i} dec ({nblk} blk)"
        assert back == xts_crypt(ct, k1, k2, seq, encrypt=False)
    dut._log.info("XTS: 12 random sectors (1..32 blocks) enc+dec vs model PASS")

async def run_sector_greedy(dut, data, key1, key2, seq, encrypt):
    """Like a real controller: start each request on the first cycle busy is low,
    i.e. on the same cycle the previous done/tweak lands. Drives on falling edges."""
    dut.key1.value = int.from_bytes(key1, "big")
    dut.key2.value = int.from_bytes(key2, "big")
    dut.sector.value = seq
    dut.dec.value = 0 if encrypt else 1
    await FallingEdge(dut.clk)
    dut.tweak_start.value = 1
    await FallingEdge(dut.clk)
    dut.tweak_start.value = 0
    blocks = [data[j:j+16] for j in range(0, len(data), 16)]
    out, sent = b"", 0
    for _ in range(64 * (len(blocks) + 1)):
        if int(dut.done.value) == 1:
            out += int(dut.dout.value).to_bytes(16, "big")
            if len(out) == len(data):
                return out
        if int(dut.busy.value) == 0 and sent < len(blocks) and int(dut.blk_start.value) == 0:
            dut.din.value = int.from_bytes(blocks[sent], "big")
            dut.blk_start.value = 1
            sent += 1
        else:
            dut.blk_start.value = 0
        await FallingEdge(dut.clk)
    raise AssertionError("timeout in greedy sector")

@cocotb.test()
async def test_xts_back_to_back(dut):
    await reset(dut)
    rnd = random.Random(0xB2B)
    k1, k2, seq, pt, ct = IEEE_VECTORS[1]
    k1, k2, pt, ct = map(bytes.fromhex, (k1, k2, pt, ct))
    assert await run_sector_greedy(dut, pt, k1, k2, seq, True) == ct, "IEEE vec#2 greedy enc"
    for i in range(4):
        k1, k2 = (bytes(rnd.randrange(256) for _ in range(16)) for _ in range(2))
        seq = rnd.getrandbits(128)
        pt = bytes(rnd.randrange(256) for _ in range(16 * 8))
        exp = xts_crypt(pt, k1, k2, seq)
        assert await run_sector_greedy(dut, pt, k1, k2, seq, True) == exp, f"greedy enc #{i}"
        assert await run_sector_greedy(dut, exp, k1, k2, seq, False) == pt, f"greedy dec #{i}"
    dut._log.info("XTS: back-to-back (start on the cycle busy drops) enc+dec PASS")
