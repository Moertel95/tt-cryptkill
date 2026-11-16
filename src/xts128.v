// xts128.v -- AES-128-XTS (IEEE 1619) wrapper over one shared aes128 core.
// No ciphertext stealing: callers feed whole 16-byte blocks only.
// Byte order: bus[127:120] = byte 0 (same as aes128 / golden model).
//
// Protocol (both starts are edge-gated and ignored while busy):
//   tweak_start : T = AES_enc(key2, sector as 128-bit little-endian)
//   blk_start   : one block, dec selects direction; done pulses when dout valid.
//                 dout stays valid until the next blk_start is accepted.
// T advances by alpha lazily, when the *next* block is accepted, so dout can be
// aes_dout ^ T combinationally with no extra 128-bit output register.
`default_nettype none

module xts128 (
    input  wire         clk,
    input  wire         rst_n,
    input  wire [127:0] key1,      // data key
    input  wire [127:0] key2,      // tweak key
    input  wire [127:0] sector,    // data-unit number, plain integer
    input  wire         tweak_start,
    input  wire         blk_start,
    input  wire         dec,
    input  wire [127:0] din,
    output wire [127:0] dout,
    output wire         busy,
    output wire         done
);

  function automatic [127:0] bswap; input [127:0] x; integer i; begin
    for (i = 0; i < 16; i = i + 1) bswap[i*8 +: 8] = x[(15-i)*8 +: 8]; end endfunction

  // multiply by alpha in GF(2^128): T is little-endian bytes, poly 0x87
  function automatic [127:0] alpha; input [127:0] t; reg [127:0] v; begin
    v = bswap(t);
    alpha = bswap({v[126:0], 1'b0} ^ (v[127] ? 128'h87 : 128'h0)); end endfunction

  reg  [127:0] T;
  reg          blk_phase, adv, req_d;
  wire [127:0] a_dout;
  wire         a_done;

  wire req    = tweak_start | blk_start;
  wire accept = req & ~req_d & ~busy;
  wire is_tw  = tweak_start;                     // tweak wins if both asserted
  wire [127:0] T_cur = adv ? alpha(T) : T;       // tweak for the block being accepted

  aes128 core (
    .clk(clk), .rst_n(rst_n), .start(accept),
    .dec(is_tw ? 1'b0 : dec),
    .key(is_tw ? key2 : key1),
    .din(is_tw ? bswap(sector) : din ^ T_cur),
    .dout(a_dout), .busy(busy), .done(a_done)
  );

  assign dout = a_dout ^ T;
  assign done = a_done & blk_phase;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      T <= 0; blk_phase <= 0; adv <= 0; req_d <= 0;
    end else begin
      req_d <= req;
      if (accept) begin
        blk_phase <= ~is_tw;
        if (is_tw) adv <= 1'b0;
        else begin T <= T_cur; adv <= 1'b1; end
      end
      if (a_done & ~blk_phase) T <= a_dout;
    end
  end
endmodule
`default_nettype wire
