#!/usr/bin/env python3
"""Generate aes128.v (iterative AES-128 enc+dec, on-the-fly key schedule).
S-box tables emitted from the verified SBOX in aes_xts_ref.py so hardware
tables are bit-identical to the golden model. Review fixes applied:
 - din/dec latched at start; start edge-gated (no auto-retrigger)
 - all functions declared `automatic`."""
from aes_xts_ref import SBOX, INV_SBOX

def byte(sig, b):
    return f"{sig}[{(15-b)*8} +: 8]"

def sbox_case(name):
    tbl = SBOX if name == "sb" else INV_SBOX
    lines = [f"  function automatic [7:0] {name}; input [7:0] a; begin case(a)"]
    for i in range(0, 256, 8):
        lines.append("    " + " ".join(f"8'h{i+j:02x}:{name}=8'h{tbl[i+j]:02x};" for j in range(8)))
    lines.append(f"    default: {name}=8'h00; endcase end endfunction")
    return "\n".join(lines)

def subbytes(fn, src):
    return "{" + ", ".join(f"{fn}({byte(src,b)})" for b in range(16)) + "}"

def shiftrows(inv):
    assigns = []
    for o in range(16):
        r, c = o % 4, o // 4
        inp = (((c - r) % 4) if inv else ((c + r) % 4)) * 4 + r
        assigns.append(f"{byte('y',o)} = {byte('s',inp)};")
    name = "inv_srows" if inv else "srows"
    return (f"  function automatic [127:0] {name}; input [127:0] s; reg [127:0] y; begin\n    "
            + "\n    ".join(assigns) + f"\n    {name} = y; end endfunction")

HEAD = r"""// aes128.v -- AES-128 iterative core, encrypt + decrypt, on-the-fly key schedule
// S-box tables generated from the FIPS-197/IEEE-1619-verified golden model.
// Latency: encrypt ~10 cycles; decrypt ~20 cycles (10 key-setup + 10 rounds).
`default_nettype none

module aes128 (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         start,
    input  wire         dec,
    input  wire [127:0] key,
    input  wire [127:0] din,
    output reg  [127:0] dout,
    output reg          busy,
    output reg          done
);
"""

GF = r"""
  function automatic [7:0] xt;  input [7:0] a; begin xt = a[7] ? ((a<<1)^8'h1b) : (a<<1); end endfunction
  function automatic [7:0] m9;  input [7:0] a; begin m9  = xt(xt(xt(a)))^a;               end endfunction
  function automatic [7:0] m11; input [7:0] a; begin m11 = xt(xt(xt(a)))^xt(a)^a;         end endfunction
  function automatic [7:0] m13; input [7:0] a; begin m13 = xt(xt(xt(a)))^xt(xt(a))^a;     end endfunction
  function automatic [7:0] m14; input [7:0] a; begin m14 = xt(xt(xt(a)))^xt(xt(a))^xt(a); end endfunction
  function automatic [31:0] mixc; input [31:0] c; reg [7:0] a0,a1,a2,a3; begin
    a0=c[31:24]; a1=c[23:16]; a2=c[15:8]; a3=c[7:0];
    mixc = { xt(a0)^(xt(a1)^a1)^a2^a3, a0^xt(a1)^(xt(a2)^a2)^a3,
             a0^a1^xt(a2)^(xt(a3)^a3), (xt(a0)^a0)^a1^a2^xt(a3) };
  end endfunction
  function automatic [31:0] invmixc; input [31:0] c; reg [7:0] a0,a1,a2,a3; begin
    a0=c[31:24]; a1=c[23:16]; a2=c[15:8]; a3=c[7:0];
    invmixc = { m14(a0)^m11(a1)^m13(a2)^m9(a3), m9(a0)^m14(a1)^m11(a2)^m13(a3),
                m13(a0)^m9(a1)^m14(a2)^m11(a3), m11(a0)^m13(a1)^m9(a2)^m14(a3) };
  end endfunction
  function automatic [127:0] mixcols; input [127:0] s; begin
    mixcols = {mixc(s[127:96]),mixc(s[95:64]),mixc(s[63:32]),mixc(s[31:0])}; end endfunction
  function automatic [127:0] invmixcols; input [127:0] s; begin
    invmixcols = {invmixc(s[127:96]),invmixc(s[95:64]),invmixc(s[63:32]),invmixc(s[31:0])}; end endfunction
  function automatic [31:0] subword; input [31:0] w; begin
    subword = {sb(w[31:24]),sb(w[23:16]),sb(w[15:8]),sb(w[7:0])}; end endfunction
  function automatic [31:0] rotword; input [31:0] w; begin rotword = {w[23:0],w[31:24]}; end endfunction
  function automatic [7:0] rcon; input [3:0] r; begin case(r)
     4'd1:rcon=8'h01;4'd2:rcon=8'h02;4'd3:rcon=8'h04;4'd4:rcon=8'h08;4'd5:rcon=8'h10;
     4'd6:rcon=8'h20;4'd7:rcon=8'h40;4'd8:rcon=8'h80;4'd9:rcon=8'h1b;4'd10:rcon=8'h36;
     default:rcon=8'h00; endcase end endfunction
  function automatic [127:0] kexp_fwd; input [127:0] k; input [7:0] rc; reg [31:0] w0,w1,w2,w3,t; begin
    w0=k[127:96];w1=k[95:64];w2=k[63:32];w3=k[31:0];
    t = subword(rotword(w3)) ^ {rc,24'b0};
    w0=w0^t;w1=w1^w0;w2=w2^w1;w3=w3^w2; kexp_fwd={w0,w1,w2,w3}; end endfunction
  function automatic [127:0] kexp_rev; input [127:0] k; input [7:0] rc; reg [31:0] a0,a1,a2,a3,b0,b1,b2,b3,t; begin
    a0=k[127:96];a1=k[95:64];a2=k[63:32];a3=k[31:0];
    b3=a3^a2;b2=a2^a1;b1=a1^a0; t=subword(rotword(b3))^{rc,24'b0}; b0=a0^t;
    kexp_rev={b0,b1,b2,b3}; end endfunction
"""

def rounds():
    return ("\n  function automatic [127:0] enc_round; input [127:0] s; input [127:0] k; input last; reg [127:0] a,b,c; begin\n"
            f"    a = {subbytes('sb','s')};\n    b = srows(a);\n    c = last ? b : mixcols(b);\n    enc_round = c ^ k;\n  end endfunction\n"
            "  function automatic [127:0] dec_round; input [127:0] s; input [127:0] k; input last; reg [127:0] a,b,c; begin\n"
            f"    a = inv_srows(s);\n    b = {subbytes('isb','a')};\n    c = b ^ k;\n    dec_round = last ? c : invmixcols(c);\n  end endfunction\n")

FSM = r"""
  reg [127:0] st, rk, din_q;
  reg [3:0]   rnd;
  reg         setup, active, mode, start_d;
  wire [127:0] rkf = kexp_fwd(rk, rcon(rnd));
  wire [127:0] rkr = kexp_rev(rk, rcon(rnd));
  wire        start_pulse = start & ~start_d & ~active;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      st<=0; rk<=0; din_q<=0; rnd<=0; setup<=0; active<=0; mode<=0; start_d<=0;
      busy<=0; done<=0; dout<=0;
    end else begin
      done    <= 1'b0;
      start_d <= start;
      if (start_pulse) begin
        rk <= key; din_q <= din; mode <= dec; busy <= 1'b1; active <= 1'b1; rnd <= 4'd1;
        if (dec) begin st <= din;        setup <= 1'b1; end
        else     begin st <= din ^ key;  setup <= 1'b0; end
      end else if (active) begin
        if (!mode) begin
          st <= enc_round(st, rkf, (rnd==4'd10)); rk <= rkf;
          if (rnd==4'd10) begin dout <= enc_round(st, rkf, 1'b1); done<=1'b1; busy<=1'b0; active<=1'b0; end
          else rnd <= rnd + 4'd1;
        end else if (setup) begin
          rk <= rkf;
          if (rnd==4'd10) begin st <= din_q ^ rkf; setup <= 1'b0; rnd <= 4'd10; end
          else rnd <= rnd + 4'd1;
        end else begin
          st <= dec_round(st, rkr, (rnd==4'd1)); rk <= rkr;
          if (rnd==4'd1) begin dout <= dec_round(st, rkr, 1'b1); done<=1'b1; busy<=1'b0; active<=1'b0; end
          else rnd <= rnd - 4'd1;
        end
      end
    end
  end
endmodule
`default_nettype wire
"""

def main():
    parts = [HEAD, sbox_case("sb"), sbox_case("isb"), shiftrows(False), shiftrows(True), GF, rounds(), FSM]
    out = "\n".join(parts) + "\n"
    open("aes128.v","w").write(out)
    print("wrote aes128.v:", out.count(chr(10)), "lines")

if __name__ == "__main__":
    main()
