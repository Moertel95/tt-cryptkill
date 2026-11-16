#!/usr/bin/env python3
"""AES-128 + AES-128-XTS reference model (pure Python, no deps).
Doubles as the bit-exact golden spec for the RTL. Verified against:
 - FIPS-197 App. C.1  (AES-128 single block)
 - IEEE 1619-2007 XTS vectors #1 and #2
"""

SBOX = [
0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16]
INV_SBOX = [0]*256
for _i, _v in enumerate(SBOX):
    INV_SBOX[_v] = _i
RCON = [0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1b,0x36]

def gmul(a, b):
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xff
        if hi:
            a ^= 0x1b
        b >>= 1
    return p

def key_expansion(key):
    w = [list(key[4*i:4*i+4]) for i in range(4)]
    for i in range(4, 44):
        t = list(w[i-1])
        if i % 4 == 0:
            t = t[1:] + t[:1]
            t = [SBOX[b] for b in t]
            t[0] ^= RCON[i//4 - 1]
        w.append([w[i-4][j] ^ t[j] for j in range(4)])
    return w

def add_round_key(s, w, rnd):
    for c in range(4):
        for r in range(4):
            s[c*4+r] ^= w[rnd*4+c][r]

def shift_rows(s):
    out = [0]*16
    for r in range(4):
        for c in range(4):
            out[c*4+r] = s[((c+r) % 4)*4 + r]
    return out

def inv_shift_rows(s):
    out = [0]*16
    for r in range(4):
        for c in range(4):
            out[c*4+r] = s[((c-r) % 4)*4 + r]
    return out

def mix_columns(s):
    out = [0]*16
    for c in range(4):
        col = s[c*4:c*4+4]
        out[c*4+0] = gmul(col[0],2) ^ gmul(col[1],3) ^ col[2] ^ col[3]
        out[c*4+1] = col[0] ^ gmul(col[1],2) ^ gmul(col[2],3) ^ col[3]
        out[c*4+2] = col[0] ^ col[1] ^ gmul(col[2],2) ^ gmul(col[3],3)
        out[c*4+3] = gmul(col[0],3) ^ col[1] ^ col[2] ^ gmul(col[3],2)
    return out

def inv_mix_columns(s):
    out = [0]*16
    for c in range(4):
        col = s[c*4:c*4+4]
        out[c*4+0] = gmul(col[0],14)^gmul(col[1],11)^gmul(col[2],13)^gmul(col[3],9)
        out[c*4+1] = gmul(col[0],9)^gmul(col[1],14)^gmul(col[2],11)^gmul(col[3],13)
        out[c*4+2] = gmul(col[0],13)^gmul(col[1],9)^gmul(col[2],14)^gmul(col[3],11)
        out[c*4+3] = gmul(col[0],11)^gmul(col[1],13)^gmul(col[2],9)^gmul(col[3],14)
    return out

def aes_encrypt(pt, key):
    w = key_expansion(key)
    s = list(pt)
    add_round_key(s, w, 0)
    for rnd in range(1, 10):
        s = [SBOX[b] for b in s]
        s = shift_rows(s)
        s = mix_columns(s)
        add_round_key(s, w, rnd)
    s = [SBOX[b] for b in s]
    s = shift_rows(s)
    add_round_key(s, w, 10)
    return bytes(s)

def aes_decrypt(ct, key):
    w = key_expansion(key)
    s = list(ct)
    add_round_key(s, w, 10)
    for rnd in range(9, 0, -1):
        s = inv_shift_rows(s)
        s = [INV_SBOX[b] for b in s]
        add_round_key(s, w, rnd)
        s = inv_mix_columns(s)
    s = inv_shift_rows(s)
    s = [INV_SBOX[b] for b in s]
    add_round_key(s, w, 0)
    return bytes(s)

def gf_alpha(t):
    """Multiply 16-byte little-endian value by alpha (x) in GF(2^128), poly reduction 0x87."""
    t = list(t)
    carry = 0
    for k in range(16):
        newcarry = (t[k] >> 7) & 1
        t[k] = ((t[k] << 1) | carry) & 0xff
        carry = newcarry
    if carry:
        t[0] ^= 0x87
    return bytes(t)

def xts_crypt(data, key1, key2, seq, encrypt=True):
    T = aes_encrypt(seq.to_bytes(16, 'little'), key2)
    out = b''
    for j in range(0, len(data), 16):
        blk = data[j:j+16]
        xx = bytes(a ^ b for a, b in zip(blk, T))
        yy = aes_encrypt(xx, key1) if encrypt else aes_decrypt(xx, key1)
        out += bytes(a ^ b for a, b in zip(yy, T))
        T = gf_alpha(T)
    return out

def h(s):
    return bytes.fromhex(s)

if __name__ == "__main__":
    ok = True

    # 1) FIPS-197 App C.1
    k = h("000102030405060708090a0b0c0d0e0f")
    p = h("00112233445566778899aabbccddeeff")
    exp = h("69c4e0d86a7b0430d8cdb78070b4c55a")
    c = aes_encrypt(p, k)
    print("AES-128 enc FIPS-197 :", "PASS" if c == exp else "FAIL", c.hex())
    ok &= c == exp
    d = aes_decrypt(c, k)
    print("AES-128 dec roundtrip:", "PASS" if d == p else "FAIL", d.hex())
    ok &= d == p

    # extra AESAVS VarKey
    c2 = aes_encrypt(h("00000000000000000000000000000000"),
                     h("80000000000000000000000000000000"))
    print("AES-128 VarKey KAT   :", "PASS" if c2 == h("0edd33d3c621e546455bd8ba1418bec8") else "FAIL", c2.hex())
    ok &= c2 == h("0edd33d3c621e546455bd8ba1418bec8")

    # 2) IEEE 1619 XTS vector #1 (all zero)
    ct = xts_crypt(h("00"*32), h("00"*16), h("00"*16), 0)
    exp1 = h("917cf69ebd68b2ec9b9fe9a3eadda692cd43d2f59598ed858c02c2652fbf922e")
    print("XTS-AES-128 vec#1    :", "PASS" if ct == exp1 else "FAIL", ct.hex())
    ok &= ct == exp1

    # 3) IEEE 1619 XTS vector #2 (seq 0x3333333333)
    ct2 = xts_crypt(h("44"*32), h("11"*16), h("22"*16), 0x3333333333)
    exp2 = h("c454185e6a16936e39334038acef838bfb186fff7480adc4289382ecd6d394f0")
    print("XTS-AES-128 vec#2    :", "PASS" if ct2 == exp2 else "FAIL", ct2.hex())
    ok &= ct2 == exp2

    # XTS decrypt roundtrip
    pt2 = xts_crypt(ct2, h("11"*16), h("22"*16), 0x3333333333, encrypt=False)
    print("XTS-AES-128 dec rt   :", "PASS" if pt2 == h("44"*32) else "FAIL", pt2.hex())
    ok &= pt2 == h("44"*32)

    print("\nALL:", "PASS" if ok else "FAIL")
