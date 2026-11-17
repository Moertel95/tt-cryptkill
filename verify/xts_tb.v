// cocotb test harness: instantiates the XTS wrapper (with its aes128 core).
`default_nettype none
`timescale 1ns/1ps
module xts_tb;
  reg clk = 0, rst_n = 0, tweak_start = 0, blk_start = 0, dec = 0, tamper = 0, key_wr = 0;
  reg [7:0] key_byte = 0;
  reg [127:0] sector = 0, din = 0;
  wire [127:0] dout;
  wire busy, done;
  xts128 dut(.clk(clk), .rst_n(rst_n), .tamper(tamper), .key_wr(key_wr), .key_byte(key_byte), .sector(sector),
             .tweak_start(tweak_start), .blk_start(blk_start), .dec(dec),
             .din(din), .dout(dout), .busy(busy), .done(done));
  always #5 clk = ~clk;   // 100 MHz
  initial begin
    $dumpfile("xts_tb.vcd");
    $dumpvars(0, xts_tb);
  end
endmodule
