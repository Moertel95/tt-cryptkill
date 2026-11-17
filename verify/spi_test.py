"""cocotb tests for the SPI-NOR master (src/spi_nor.v) against a behavioural
W25Q flash model that also checks the wire protocol (mode 0, byte-aligned CS,
tSHSL, MOSI setup/hold, WEL before program/erase, nothing but 05 while busy).
MISO is driven 'x' between SCK fall and tCLQV, so a mistimed sample fails."""
import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge
from flash_model import W25Q, Image, MASK24

CLK_NS = 20          # 50 MHz system clock -> 25 MHz SCK
OP_READ, OP_PROG, OP_ERASE, OP_NOP = 0, 1, 2, 3


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
