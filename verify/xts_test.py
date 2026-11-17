"""cocotb test for the AES-128-XTS wrapper: IEEE-1619 vectors #1/#2 plus
randomized multi-block sectors (enc + dec), all checked against the golden
model ../model/aes_xts_ref.py::xts_crypt."""
import os, sys, random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge

CYC = 400   # > byte-serial core latency (enc 248, dec 289 clk)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "model"))
from aes_xts_ref import xts_crypt  # noqa: E402

async def pulse(dut, sig):
    sig.value = 1
    await RisingEdge(dut.clk)
    sig.value = 0
    await RisingEdge(dut.clk)

async def load_keys(dut, key1: bytes, key2: bytes):
    """32 key_wr cycles: the 256-bit XTS key, key1 byte 0 first."""
    for b in key1 + key2:
        dut.key_byte.value, dut.key_wr.value = b, 1
        await RisingEdge(dut.clk)
    dut.key_wr.value = 0

async def wait_idle(dut):
    for _ in range(CYC):
        if int(dut.busy.value) == 0:
            return
        await RisingEdge(dut.clk)
    raise AssertionError("timeout waiting for !busy")

async def run_sector(dut, data: bytes, key1: bytes, key2: bytes, seq: int, encrypt: bool) -> bytes:
    assert len(data) % 16 == 0
    await load_keys(dut, key1, key2)
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
        for _ in range(CYC):
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
    await load_keys(dut, key1, key2)
    dut.sector.value = seq
    dut.dec.value = 0 if encrypt else 1
    await FallingEdge(dut.clk)
    dut.tweak_start.value = 1
    await FallingEdge(dut.clk)
    dut.tweak_start.value = 0
    blocks = [data[j:j+16] for j in range(0, len(data), 16)]
    out, sent = b"", 0
    for _ in range(CYC * (len(blocks) + 1)):
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


# every register that holds key material, or data derived from it, must read 0
SECRETS = ["key1", "key2", "T", "core.rk", "core.st", "core.dout"]

def secrets_nonzero(dut):
    x = dut.dut
    vals = {"key1": x.key1, "key2": x.key2, "T": x.T,
            "core.rk": x.core.rk, "core.st": x.core.st, "core.dout": x.core.dout}
    return [n for n in SECRETS if int(vals[n].value) != 0]

@cocotb.test()
async def test_xts_tamper_erase(dut):
    """Crypto-erase: TAMPER mid-operation zeroes keys, T, core rk/st/dout and
    aborts the op; the same ciphertext then decrypts to garbage until the key
    is reloaded; key loads are ignored while TAMPER is held."""
    await reset(dut)
    k1, k2, seq, pt, ct = IEEE_VECTORS[1]
    k1, k2, pt, ct = map(bytes.fromhex, (k1, k2, pt, ct))
    rnd = random.Random(0x7A)

    for when in (5, 100, 260):           # tamper during tweak, mid-block, late in a dec block
        assert await run_sector(dut, pt, k1, k2, seq, True) == ct, "known-answer before tamper"
        dut.sector.value = seq
        await pulse(dut, dut.tweak_start)
        await wait_idle(dut)
        dut.din.value, dut.dec.value = int.from_bytes(ct[:16], "big"), 1
        await pulse(dut, dut.blk_start)
        for _ in range(when):
            await RisingEdge(dut.clk)
        assert int(dut.busy.value) == 1 and secrets_nonzero(dut), "op should be in flight"
        dut.tamper.value = 1             # single-cycle pulse, async to the op
        await RisingEdge(dut.clk)
        dut.tamper.value = 0
        for _ in range(2):               # 2-FF synchronizer -> erased within 2 clk
            await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        left = secrets_nonzero(dut)
        assert not left, f"tamper@{when}: not erased: {left}"
        assert int(dut.busy.value) == 0 and int(dut.dout.value) == 0
        for _ in range(CYC):             # aborted op never completes
            await RisingEdge(dut.clk)
            assert int(dut.done.value) == 0, "done after tamper"
        assert not secrets_nonzero(dut)

        # no reload: decrypting the same sector must NOT give the plaintext
        dut.sector.value = seq
        await pulse(dut, dut.tweak_start)
        await wait_idle(dut)
        got = b""
        for j in range(0, len(ct), 16):
            dut.din.value, dut.dec.value = int.from_bytes(ct[j:j+16], "big"), 1
            await pulse(dut, dut.blk_start)
            while not int(dut.done.value):
                await RisingEdge(dut.clk)
            got += int(dut.dout.value).to_bytes(16, "big")
        assert got != pt, "plaintext recovered after crypto-erase"
        assert got == xts_crypt(ct, bytes(16), bytes(16), seq, encrypt=False), "post-erase key not all-zero"

    # key loads are ignored while tamper is held; erase holds for the whole pulse
    dut.tamper.value = 1
    for _ in range(3):
        await RisingEdge(dut.clk)
    await load_keys(dut, bytes(rnd.randrange(1, 256) for _ in range(16)), k2)
    await FallingEdge(dut.clk)
    assert not secrets_nonzero(dut), "key loaded during tamper"
    dut.tamper.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    # erase is not permanent: reload -> known answer again
    assert await run_sector(dut, ct, k1, k2, seq, False) == pt, "reload after tamper"
    dut._log.info("XTS: TAMPER crypto-erase PASS")
