"""cocotb tests for the SPI-NOR master (src/spi_nor.v) against a behavioural
W25Q flash model that also checks the wire protocol (mode 0, byte-aligned CS,
tSHSL, MOSI setup/hold, WEL before program/erase, nothing but 05 while busy).
MISO is driven 'x' between SCK fall and tCLQV, so a mistimed sample fails."""
import random
import cocotb
from cocotb.binary import BinaryValue
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Edge, First, Timer
from cocotb.utils import get_sim_time

CLK_NS = 20          # 50 MHz system clock -> 25 MHz SCK
T_SHSL, T_SETUP, T_HOLD, T_CLQV = 50, 5, 5, 7   # ns, W25Q-class datasheet minimums / max
OP_READ, OP_PROG, OP_ERASE, OP_NOP = 0, 1, 2, 3
MASK24 = 0xFFFFFF


class W25Q:
    def __init__(self, dut, rnd, busy_max=4):
        self.d, self.rnd, self.busy_max = dut, rnd, busy_max
        self.mem, self.wel, self.busy = {}, False, 0
        self.txns, self.errors = [], []
        self.last_mosi = self.last_rise = self.last_cs_rise = -1e9
        dut.miso.value = BinaryValue("z")
        cocotb.start_soon(self._mosi_watch())
        cocotb.start_soon(self._run())

    def now(self):
        return get_sim_time("ns")

    def err(self, msg):
        self.errors.append(f"{self.now():.0f}ns {msg}")

    async def _mosi_watch(self):
        while True:
            await Edge(self.d.mosi)
            if int(self.d.cs_n.value) == 0 and self.now() - self.last_rise < T_HOLD:
                self.err("MOSI hold violated")
            self.last_mosi = self.now()

    async def _run(self):
        d = self.d
        while True:
            await FallingEdge(d.cs_n)
            if self.now() - self.last_cs_rise < T_SHSL:
                self.err(f"tSHSL: CS high only {self.now() - self.last_cs_rise:.0f}ns")
            if int(d.sck.value) != 0:
                self.err("SCK not low at CS fall (mode 0)")
            await self._txn()
            self.last_cs_rise = self.now()
            d.miso.value = BinaryValue("z")

    async def _txn(self):
        d = self.d
        got, cur, nbits, out, obyte, obits = [], 0, 0, None, 0, 0
        while True:
            rise, fall, csr = RisingEdge(d.sck), FallingEdge(d.sck), RisingEdge(d.cs_n)
            t = await First(rise, fall, csr)
            if t is csr:
                break
            if t is rise:
                if self.now() - self.last_mosi < T_SETUP:
                    self.err("MOSI setup violated")
                self.last_rise = self.now()
                cur = (cur << 1) | int(d.mosi.value)
                nbits += 1
                if nbits == 8:
                    got.append(cur)
                    cur, nbits = 0, 0
                    out = self._on_byte(got, out)
            elif out is not None:   # SCK fell: shift out next bit after tCLQV
                if obits == 0:
                    obyte, obits = next(out), 8
                d.miso.value = BinaryValue("x")
                await Timer(T_CLQV, "ns")
                obits -= 1
                d.miso.value = (obyte >> obits) & 1
        self._finish(got, nbits)

    def _status(self):
        while True:
            st = (1 if self.busy else 0) | (2 if self.wel else 0)
            self.busy = max(0, self.busy - 1)
            yield st

    def _read(self, a):
        while True:
            yield self.mem.get(a, 0xFF)
            a = (a + 1) & MASK24

    def _on_byte(self, b, out):
        if len(b) == 1:
            if self.busy and b[0] != 0x05:
                self.err(f"cmd {b[0]:02x} while busy")
            if b[0] == 0x05:
                return self._status()
        if len(b) == 4 and b[0] == 0x03:
            return self._read((b[1] << 16) | (b[2] << 8) | b[3])
        return out

    def _finish(self, b, nbits):
        self.txns.append(bytes(b))
        if nbits:
            self.err(f"CS rose mid-byte ({nbits} bits)")
            return
        if not b:
            self.err("empty CS window")
            return
        op, a = b[0], ((b[1] << 16) | (b[2] << 8) | b[3]) if len(b) >= 4 else None
        if op == 0x06:
            if len(b) != 1: self.err("06 with extra bytes")
            self.wel = True
        elif op in (0x02, 0x20):
            if not self.wel:
                self.err(f"{op:02x} without WEL")
                return
            if op == 0x02:
                data = b[4:]
                if not 1 <= len(data) <= 256: self.err(f"PP with {len(data)} bytes")
                for i, v in enumerate(data):   # program can only clear bits; wraps inside the page
                    pa = (a & ~0xFF) | ((a + i) & 0xFF)
                    self.mem[pa] = self.mem.get(pa, 0xFF) & v
            else:
                if len(b) != 4: self.err("20 with extra bytes")
                for pa in range(a & ~0xFFF, (a & ~0xFFF) + 4096):
                    self.mem.pop(pa, None)
            self.wel = False
            self.busy = self.rnd.randint(0, self.busy_max)
        elif op not in (0x03, 0x05):
            self.err(f"unknown opcode {op:02x}")


class Image:
    """Independent expected flash contents (test oracle)."""
    def __init__(self):
        self.m = {}
    def erase(self, a):
        for pa in range(a & ~0xFFF, (a & ~0xFFF) + 4096):
            self.m.pop(pa, None)
    def prog(self, a, data):
        for i, v in enumerate(data):
            pa = (a & ~0xFF) | ((a + i) & 0xFF)
            self.m[pa] = self.m.get(pa, 0xFF) & v
    def read(self, a, n):
        return bytes(self.m.get((a + i) & MASK24, 0xFF) for i in range(n))


async def setup(dut, seed, busy_max=4):
    cocotb.start_soon(Clock(dut.clk, CLK_NS, units="ns").start())
    flash = W25Q(dut, random.Random(seed), busy_max)
    dut.rst_n.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    return flash


async def run_op(dut, op, addr, n=0, wdata=b"", rnd=None, p=1.0, start_cycles=1):
    """Drive one op on falling edges; p = probability rready/wvalid is high per cycle."""
    rnd = rnd or random.Random(0)
    await FallingEdge(dut.clk)
    dut.op.value, dut.addr.value, dut.len.value = op, addr, n
    dut.start.value = 1
    got, wi, seen_done = bytearray(), 0, False
    for cyc in range(60 * (n + 40) + start_cycles):
        if cyc == start_cycles:
            dut.start.value = 0
        seen_done |= bool(int(dut.done.value))
        if int(dut.wready.value):
            wi += 1
        r = rnd.random() < p
        if int(dut.rvalid.value) and r:
            got.append(int(dut.rdata.value))   # rvalid&rready meet at the next rising edge
        dut.rready.value = r
        if wi < len(wdata):
            dut.wdata.value, dut.wvalid.value = wdata[wi], rnd.random() < p
        else:
            dut.wvalid.value = 0
        if (cyc >= start_cycles and seen_done and (op != OP_READ or len(got) == n)
                and not (int(dut.rvalid.value) and r)):
            dut.rready.value = 0
            assert wi == len(wdata), f"master took {wi} of {len(wdata)} write bytes"
            return bytes(got)
        await FallingEdge(dut.clk)
    raise AssertionError(f"timeout op={op} addr={addr:06x} n={n}")


@cocotb.test()
async def test_spi_wire_format(dut):
    """Exact command bytes on the wire (KAT) + basic read/program/erase."""
    flash = await setup(dut, 1)
    flash.mem.update({0x123456 + i: v for i, v in enumerate(b"\xde\xad\xbe\xef")})
    assert await run_op(dut, OP_READ, 0x123456, 4) == b"\xde\xad\xbe\xef"
    assert flash.txns[-1] == bytes([0x03, 0x12, 0x34, 0x56, 0, 0, 0, 0])

    n0 = len(flash.txns)
    await run_op(dut, OP_ERASE, 0x00A123)
    t = flash.txns[n0:]
    assert t[0] == b"\x06" and t[1] == bytes([0x20, 0x00, 0xA1, 0x23]), t
    assert t[2][0] == 0x05 and all(x == 0 for x in t[2][1:]) and len(t) == 3, t

    n0 = len(flash.txns)
    await run_op(dut, OP_PROG, 0x00AB10, 2, b"\xa5\x5a")
    t = flash.txns[n0:]
    assert t[0] == b"\x06" and t[1] == bytes([0x02, 0x00, 0xAB, 0x10, 0xA5, 0x5A]), t
    assert t[2][0] == 0x05 and len(t) == 3, t
    assert await run_op(dut, OP_READ, 0x00AB0F, 4) == b"\xff\xa5\x5a\xff"
    assert not flash.errors, flash.errors
    dut._log.info("SPI: wire-format KAT PASS")


@cocotb.test()
async def test_spi_random(dut):
    """Random erase/program/read with random backpressure vs an independent image."""
    flash = await setup(dut, 2)
    rnd, img = random.Random(0x5F1), Image()
    sectors = [0x000000, 0x001000, 0x7FF000, 0xFFF000]   # incl. top of the 16 MB space
    for s in sectors:
        await run_op(dut, OP_ERASE, s + rnd.randrange(4096), rnd=rnd)   # any addr in sector erases it
        img.erase(s)
    for i in range(60):
        p = rnd.choice([1.0, 0.7, 0.3])
        s = rnd.choice(sectors)
        kind = rnd.random()
        if kind < 0.1:
            a = s + rnd.randrange(4096)
            await run_op(dut, OP_ERASE, a, rnd=rnd, p=p)
            img.erase(a)
        elif kind < 0.55:
            page = s + 256 * rnd.randrange(16)
            off = rnd.randrange(256)
            n = rnd.choice([1, 256 - off, rnd.randint(1, 256 - off)])
            data = bytes(rnd.randrange(256) for _ in range(n))
            await run_op(dut, OP_PROG, page + off, n, data, rnd=rnd, p=p)
            img.prog(page + off, data)
        else:
            a = (s + rnd.randrange(4096) - 100) & MASK24   # may straddle sectors / wrap 0xFFFFFF->0
            n = rnd.randint(1, 300)
            got = await run_op(dut, OP_READ, a, n, rnd=rnd, p=p)
            assert got == img.read(a, n), f"#{i} read {a:06x}+{n}"
    for s in sectors:   # len is 12 bits (max 4095): read each sector as two halves
        for h in (s, s + 2048):
            assert await run_op(dut, OP_READ, h, 2048, rnd=rnd) == img.read(h, 2048), f"{h:06x}"
    assert not flash.errors, flash.errors
    dut._log.info("SPI: 60 random ops + full readback with backpressure PASS")


@cocotb.test()
async def test_spi_edges(dut):
    flash = await setup(dut, 3, busy_max=0)
    # len=0 PROGRAM and op 3: done, no flash traffic at all
    for op in (OP_PROG, OP_NOP):
        n0 = len(flash.txns)
        await run_op(dut, op, 0x000100, 0)
        assert len(flash.txns) == n0, flash.txns[n0:]
    # len=0 READ: header only, no data
    assert await run_op(dut, OP_READ, 0x000100, 0) == b""
    # start held high far longer than the op => exactly one op
    n0 = len(flash.txns)
    await run_op(dut, OP_READ, 0x000000, 1, start_cycles=300)
    assert len(flash.txns) == n0 + 1, flash.txns[n0:]
    # long WIP: master must keep polling inside one CS window
    await run_op(dut, OP_ERASE, 0x002000)
    flash.rnd, flash.busy_max = random.Random(9), 40
    n0 = len(flash.txns)
    await run_op(dut, OP_PROG, 0x002000, 1, b"\x00")
    poll = flash.txns[n0 + 2]
    assert poll[0] == 0x05 and len(poll) >= 2, poll
    assert await run_op(dut, OP_READ, 0x002000, 1) == b"\x00"
    # back-to-back: next start right after done (tSHSL checked by the model)
    for k in range(4):
        await run_op(dut, OP_READ, 0x002000 + k, 1)
    assert not flash.errors, flash.errors
    dut._log.info("SPI: edge cases PASS")
