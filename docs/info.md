## How it works

CryptKill is a self-encrypting storage controller. Everything the host writes is
encrypted with **AES-128 in XTS mode** (IEEE 1619, the mode used by disk
encryption) before it reaches an external SPI-NOR flash. The 256-bit XTS key lives
only in on-chip registers. The headline feature is **hardware crypto-erase**:
raising the TAMPER pin clears the keys, the tweak, the AES core's round-key and
state registers, the block buffer and the SPI master within 2 clock cycles. The
ciphertext stays in the flash, but without the key it can no longer be decrypted.

Inside the chip:

- a byte-serial AES-128 core (encrypt + decrypt, one shared S-box pair, about
  250-290 cycles per block), wrapped in an XTS engine (tweak = AES(Key2, sector),
  multiply by alpha per block);
- an SPI-NOR master (mode 0, SCK = clk/2; read 03, page program 06/02/05, 4 KB
  erase 06/20/05);
- a host state machine driven over a byte-wide 4-phase handshake.

This is an honest, inspectable demonstrator of key binding and instant
crypto-erase using standard AES, not a certified security product. Erase needs a
running clock and a TAMPER pulse of at least one clock. It gives no protection
against physical, probing or power-analysis attacks.

### Host protocol

Each byte is one handshake:

1. Put the byte on `ui[7:0]`. Set `HOST_CMD` to 1 for a command or 0 for data.
2. Raise `HOST_VALID`.
3. Wait for `ACK`.
4. Drop `HOST_VALID` and wait for `ACK` to fall.

`ACK` rises only once the byte, and any flash or AES work it started, is
finished.

| Cmd | Data bytes | Action |
|-----|------------|--------|
| `01` LOAD_KEY | 32 (Key1 byte 0 first, then Key2) | Load the XTS key. Clears KEY_OK and SEC_OK, so a key change mid-sector forces a new SET_SECTOR. |
| `02` SET_SECTOR | 2 (big-endian, 15-bit sector n) | Compute the tweak and reset the block index j to 0. Needs KEY_OK. Flash address = n*512. |
| `03` WRITE_BLOCK | 16 plaintext | Encrypt block j, program it at n*512+16j, then j++. |
| `04` READ_BLOCK | none | Read and decrypt block j, then j++. After `ACK`, `uo` shows plaintext byte 0. Each further handshake shows the next byte. The 16th handshake returns `uo` to status. |
| `05` ERASE | none | Erase the 4 KB flash sector that holds sector n. Needs SEC_OK. |

Block commands need SEC_OK and j < 32. A sector is 512 bytes, written or read
in order. A rejected byte is still ACKed and sets ERR, which the next command
clears. A command byte sent while data bytes are expected aborts the command.
Check the status before READ_BLOCK: it is refused exactly when SEC_OK=0 or
FULL=1.

Status on `uo` (outside READ_BLOCK output): bit 0 KEY_OK, 1 SEC_OK, 2 ERR,
3 FULL (j = 32), 4 ERASING, 7 BUSY.

## How to test

1. Wire a W25Q-class SPI-NOR flash to `uio[3:0]` and hold its WP# and HOLD# high.
2. Drive the host pins from the RP2040 at clk = 20 MHz.
3. Run `LOAD_KEY`, `SET_SECTOR`, `ERASE`, then 32 x `WRITE_BLOCK`. Read the raw
   flash: it holds AES-XTS ciphertext.
4. Run `SET_SECTOR` again, then 32 x `READ_BLOCK`. You get the plaintext back.
5. Pulse `TAMPER` (`uio[7]`). Status reads 0, and `SET_SECTOR` / `READ_BLOCK` are
   refused.
6. Load any other key: the sector reads as random garbage. Only the original key
   restores it.

The cocotb test in `test/test.py` runs this same sequence through the pins
against a protocol-checking flash model.

## External hardware

- An SPI-NOR flash (W25Q32/64/128 or similar), 3.3 V, single-bit SPI on
  `uio[0..3]` (CS#, SCK, MOSI=DI, MISO=DO), with WP# and HOLD# tied high.
- The host (the RP2040 on the TT demo board) drives `ui[7:0]`, `HOST_VALID`,
  `HOST_CMD` and `TAMPER`, and reads `uo[7:0]` and `ACK`.
- An optional tamper switch on `uio[7]` (active high).
