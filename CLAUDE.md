# CryptKill — TinyTapeout AES-128-XTS self-encrypting controller

Handoff/context file. Read this first. It is the single source of truth for
continuing this project in any fresh session (Claude Code or chat).

## What this chip is
A self-encrypting storage controller for TinyTapeout (open-source SKY130 ASIC).
It transparently encrypts every byte written to a commodity SPI-NOR flash under
a key held only on-die, and its headline feature is **hardware crypto-erase**:
a TAMPER pin zeroizes the key register in one clock, so the flash contents
become permanently unrecoverable in microseconds. Target audience:
military / cyber data-at-rest. Framing: an honest, inspectable *demonstrator*
of key-binding + instant crypto-erase using standard AES — not a certified
product. Do NOT roll custom crypto; standard AES only.

## Locked spec
- Cipher/mode: **AES-128 in XTS mode** (IEEE 1619 / NIST SP 800-38E). Two
  128-bit keys (Key1 = data, Key2 = tweak) => 256 bits of key material.
- Tweak: `T0 = AES_enc(Key2, sector_number_as_128bit_LE)`; per 16-byte block
  multiply T by alpha in GF(2^128), reduction poly 0x87 (1-bit left shift,
  little-endian, XOR 0x87 into byte 0 on carry-out).
- No ciphertext stealing: fix the data unit (sector) to a multiple of 16 bytes.
- Storage: SPI NOR flash (W25Q-class), controller = SPI master.
- Host / test driver: RP2040 on the TT demo board drives the pins; key loaded
  via a protected command (UART-style) at power-up.
- Crypto-erase: a TAMPER input pin clears BOTH key registers in 1 clock.
- Device-bind (stretch, later): `effective_key = key XOR H(device_id)` where
  device_id is strapped on spare pins — deterministic, simulable. A real RO-PUF
  is a silicon-only upgrade path, never a demo dependency (can't verify pre-fab).
- Tiles: target **2x2** (AES enc+decrypt + 256-bit key + XTS + SPI). Confirm
  after first synthesis. Shuttle: `ttsky-verilog-template`, TTSKY26d/26e (SKY130).
  Pace: opportunistic for the 2026-11-30 close, otherwise the next shuttle.
  Result > speed.

## Verification model (IMPORTANT)
- There is a **pure-Python golden model** at `model/aes_xts_ref.py`, verified
  bit-exact against FIPS-197 and IEEE-1619 XTS vectors. Treat it as ground truth
  for byte ordering and algorithm. All RTL is written to match it.
- Verilog is verified via **GitHub Actions CI** (`.github/workflows/aes.yaml`
  installs Icarus Verilog + cocotb and runs the tests). If you have a local
  simulator (iverilog + cocotb), run `make -C verify` locally too.
- cocotb tests live under `verify/` and check the RTL against the golden model
  (fixed KATs + randomized vectors).

## Status
- DONE: `src/aes128.v` — iterative AES-128, encrypt **and** decrypt, on-the-fly
  key schedule (forward for enc; 10-cycle forward setup then reverse schedule
  for dec). `din`/`dec` latched at `start`; `start` is edge-gated; functions are
  `automatic`. S-box tables are generated from the golden model by
  `tools/gen_aes.py` (regenerate with `cd tools && python3 gen_aes.py` — needs
  `model/aes_xts_ref.py` importable). **CI-verified**: FIPS KAT enc+dec + 32
  random enc/dec vectors vs the model (`aes-core-test` workflow = green).

## TODO (next, in order — build one block, let CI verify, then next)
1. **XTS wrapper** over `aes128`: Key2 tweak-encrypt of the sector number,
   GF(2^128) x-alpha per block, Key1 data encrypt/decrypt, XOR. cocotb test vs
   `model/aes_xts_ref.py::xts_crypt` and the two IEEE-1619 vectors.
2. **SPI-NOR master controller** (W25Q): read/write/erase commands. Highest
   risk = command/timing correctness burned into irreversible silicon. Test
   against a simulated flash model (BFM) first; validate against a real W25Q on
   FPGA before tapeout.
3. **Key register + TAMPER zeroize**: load path + synchronous 1-clock clear of
   both keys on the TAMPER pin.
4. **Top `tt_um_cryptkill`**: pin/host protocol (shift key/data in over `ui`,
   SPI on `uio`, status on `uo`, TAMPER on a `ui` bit), wire the blocks, set
   `info.yaml` `tiles: 2x2` + pinout + source_files, write `docs/info.md`.
   Then fix the `gds` workflow (it and `docs` currently fail — they fail on the
   pristine template too, i.e. pre-existing; address at integration/submission).

## Conventions
- Keep all S-box / algorithm constants sourced from the golden model — never
  hand-type crypto tables.
- Byte order in RTL: `din[127:120]` = byte 0; AES state is column-major,
  column c = bits `[(3-c)*32 +: 32]`, `state[c*4+r]` = byte `c*4+r`.
- One verifiable block per commit; CI must stay green on `aes-core-test`.
