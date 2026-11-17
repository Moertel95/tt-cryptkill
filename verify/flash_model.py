"""Behavioural W25Q-class SPI-NOR flash model that also checks the wire protocol
(mode 0, byte-aligned CS, tSHSL, MOSI setup/hold, WEL before program/erase,
nothing but 05 while busy). MISO is driven 'x' between SCK fall and tCLQV, so a
mistimed sample fails. Needs dut.cs_n / sck / mosi (outputs) and dut.miso (a reg
the model drives). Works with cocotb 1.9 and 2.x."""
from cocotb.types import Logic
from cocotb.triggers import RisingEdge, FallingEdge, Edge, First, Timer
from cocotb.utils import get_sim_time
import cocotb

T_SHSL, T_SETUP, T_HOLD, T_CLQV = 50, 5, 5, 7   # ns, W25Q-class datasheet minimums / max
MASK24 = 0xFFFFFF
Z, X = Logic("Z"), Logic("X")


class W25Q:
    def __init__(self, dut, rnd, busy_max=4):
        self.d, self.rnd, self.busy_max = dut, rnd, busy_max
        self.mem, self.wel, self.busy = {}, False, 0
        self.txns, self.errors = [], []
        self.last_mosi = self.last_rise = self.last_cs_rise = -1e9
        dut.miso.value = Z
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
            d.miso.value = Z

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
                d.miso.value = X
                await Timer(T_CLQV, "ns")
                if int(d.cs_n.value):   # CS rose during tCLQV (e.g. master reset): end txn
                    break
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
