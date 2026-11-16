// cocotb test harness: instantiates the AES-128 core directly.
`default_nettype none
`timescale 1ns/1ps
module aes_tb;
  reg clk = 0, rst_n = 0, start = 0, dec = 0;
  reg [127:0] key = 0, din = 0;
  wire [127:0] dout;
  wire busy, done;
  aes128 dut(.clk(clk), .rst_n(rst_n), .start(start), .dec(dec),
             .key(key), .din(din), .dout(dout), .busy(busy), .done(done));
  always #5 clk = ~clk;   // 100 MHz
  initial begin
    $dumpfile("aes_tb.vcd");
    $dumpvars(0, aes_tb);
  end
endmodule
