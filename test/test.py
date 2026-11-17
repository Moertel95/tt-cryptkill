# SPDX-FileCopyrightText: © 2026 Moertel95
# SPDX-License-Identifier: Apache-2.0
"""End-to-end test of tt_um_cryptkill through its pins only: the host protocol on
ui/uo/uio against the protocol-checking W25Q flash model, checked against the
golden XTS model. Runs as RTL (`make`) and gate level (`make GATES=yes`, shorter)."""
import os
import random
import sys

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "verify"))
sys.path.insert(0, os.path.join(HERE, "..", "model"))
from flash_model import W25Q  # noqa: E402
from aes_xts_ref import xts_crypt  # noqa: E402

GL = os.environ.get("GATES") == "yes"
CLK_NS = 50                       # 20 MHz (SCK 10 MHz)
LOAD_KEY, SET_SECTOR, WRITE_BLOCK, READ_BLOCK, ERASE = 1, 2, 3, 4, 5
KEY_OK, SEC_OK, ERR, FULL, ERASING, BUSY = 1, 2, 4, 8, 16, 128


class Host:
    """RP2040 side of the 4-phase byte handshake."""
    def __init__(self, dut):
        self.d = dut

    async def _ack(self, level, limit=20000):
        for _ in range(limit):
            if int(self.d.ack.value) == level:
                return
            await RisingEdge(self.d.clk)
        raise AssertionError(f"no ACK={level}")

    async def byte(self, b, cmd):
        d = self.d
        d.ui_in.value, d.host_cmd.value, d.host_valid.value = b, cmd, 1
        await self._ack(1)
        d.host_valid.value = 0
        await self._ack(0)

    def status(self):
        return int(self.d.uo_out.value)

    async def load_key(self, k1, k2):
        await self.byte(LOAD_KEY, 1)
        for b in k1 + k2:
            await self.byte(b, 0)

    async def set_sector(self, n):
        await self.byte(SET_SECTOR, 1)
        await self.byte(n >> 8, 0)
        await self.byte(n & 0xFF, 0)

    async def write_block(self, data):
        await self.byte(WRITE_BLOCK, 1)
        for b in data:
            await self.byte(b, 0)

    async def read_block(self):
        ok = (self.status() & (SEC_OK | FULL)) == SEC_OK   # host rule: check before READ
        await self.byte(READ_BLOCK, 1)
        if not ok:
            assert self.status() & ERR, "READ_BLOCK not refused"
            return None
        out = bytearray()
        for _ in range(16):
            out.append(self.status())
            await self.byte(0, 0)
        return bytes(out)

    async def read_sector(self, n, nblk):
        await self.set_sector(n)
        return b"".join([await self.read_block() for _ in range(nblk)])


async def boot(dut, seed):
    cocotb.start_soon(Clock(dut.clk, CLK_NS, unit="ns").start())
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.host_valid.value = dut.host_cmd.value = dut.tamper.value = 0
    flash = W25Q(dut, random.Random(seed))
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
    return Host(dut), flash


def secrets(dut):
    """RTL only: registers that must be zero after TAMPER."""
    x = dut.user_project.xts
    regs = {"key1": x.key1, "key2": x.key2, "T": x.T, "core.rk": x.core.rk,
            "core.st": x.core.st, "core.dout": x.core.dout, "top.buf_q": dut.user_project.buf_q}
    return [n for n, h in regs.items() if int(h.value) != 0]


@cocotb.test(timeout_time=25, timeout_unit="ms")
async def test_cryptkill_e2e(dut):
    """Load key, write a sector, check flash holds the XTS ciphertext, read it back,
    then TAMPER: key gone, data unreadable, correct key restores it."""
    host, flash = await boot(dut, 1)
    rnd = random.Random(0xC0DE)
    nblk = 2 if GL else 32                       # GL sim is slow: 2 blocks
    k1, k2 = (bytes(rnd.randrange(256) for _ in range(16)) for _ in range(2))
    sec = 0x5A5A & 0x7FFF
    pt = bytes(rnd.randrange(256) for _ in range(16 * nblk))
    assert host.status() == 0

    await host.set_sector(sec)                   # no key yet
    assert host.status() & ERR and not host.status() & SEC_OK
    await host.load_key(k1, k2)
    assert host.status() == KEY_OK, hex(host.status())
    await host.set_sector(sec)
    assert host.status() == KEY_OK | SEC_OK
    await host.byte(ERASE, 1)
    assert host.status() == KEY_OK | SEC_OK
    for i in range(nblk):
        await host.write_block(pt[16 * i:16 * i + 16])
        assert not host.status() & ERR, f"write {i}"

    base = sec * 512
    ct = bytes(flash.mem.get(base + i, 0xFF) for i in range(16 * nblk))
    assert ct == xts_crypt(pt, k1, k2, sec), "flash != XTS ciphertext"
    assert flash.mem.get(base + 16 * nblk, 0xFF) == 0xFF, "wrote past the data"
    if nblk == 32:
        assert host.status() & FULL
        await host.write_block(bytes(16))
        assert host.status() & ERR, "33rd block accepted"
    assert await host.read_sector(sec, nblk) == pt, "readback"

    # protocol guards
    await host.set_sector(sec)
    await host.read_block()
    await host.load_key(k1, k2)                  # mid-sector key load: sector context dropped
    assert host.status() == KEY_OK
    assert await host.read_block() is None and host.status() & ERR
    await host.byte(0x77, 1)                     # unknown command
    assert host.status() & ERR
    await host.byte(0x12, 0)                     # stray data byte
    assert host.status() & ERR
    await host.set_sector(sec)
    await host.byte(WRITE_BLOCK, 1)
    await host.byte(0xAB, 0)
    await host.byte(SET_SECTOR, 1)               # command mid-data aborts the write
    assert host.status() & ERR
    assert await host.read_sector(sec, 1) == pt[:16], "aborted write changed state"

    # TAMPER in the middle of a READ_BLOCK (flash read / AES in flight)
    await host.set_sector(sec)
    assert not flash.errors, flash.errors
    dut.ui_in.value, dut.host_cmd.value, dut.host_valid.value = READ_BLOCK, 1, 1
    await ClockCycles(dut.clk, 200)
    assert host.status() & BUSY
    dut.tamper.value = 1
    await ClockCycles(dut.clk, 3)
    assert host.status() & ERASING
    if not GL:
        assert not secrets(dut), f"not erased: {secrets(dut)}"
    dut.tamper.value = 0
    await ClockCycles(dut.clk, 3)
    assert host.status() == 0 and int(dut.ack.value) == 0, hex(host.status())
    assert int(dut.cs_n.value) == 1
    # the aborted flash READ ends mid-byte: harmless for a READ, expected here
    assert len(flash.errors) == 1 and "CS rose mid-byte" in flash.errors[0], flash.errors
    flash.errors.clear()
    dut.host_valid.value = 0                     # host times out on the lost handshake
    await ClockCycles(dut.clk, 5)

    await host.set_sector(sec)                   # key is gone: nothing works
    assert host.status() & ERR and not host.status() & (KEY_OK | SEC_OK)
    await host.byte(READ_BLOCK, 1)
    assert host.status() & ERR

    await ClockCycles(dut.clk, 400)              # let the flash finish the aborted read
    w1, w2 = (bytes(rnd.randrange(256) for _ in range(16)) for _ in range(2))
    await host.load_key(w1, w2)                  # attacker key: garbage
    got = await host.read_sector(sec, nblk)
    assert got != pt and got == xts_crypt(ct, w1, w2, sec, encrypt=False), "wrong key"
    await host.load_key(k1, k2)                  # the flash itself is intact
    assert await host.read_sector(sec, nblk) == pt, "reload"
    assert not flash.errors, flash.errors
    dut._log.info(f"e2e: {nblk} blocks, tamper erase, wrong-key and reload PASS")
