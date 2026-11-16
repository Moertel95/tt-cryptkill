// cocotb test harness: SPI-NOR master; the W25Q flash model lives in spi_test.py.
`default_nettype none
`timescale 1ns/1ps
module spi_tb;
  reg clk = 0, rst_n = 0, start = 0, wvalid = 0, rready = 0;
  reg miso = 1'bz;   // driven by the Python flash model
  reg [1:0] op = 0;
  reg [23:0] addr = 0;
  reg [11:0] len = 0;
  reg [7:0] wdata = 0;
  wire [7:0] rdata;
  wire busy, done, wready, rvalid, sck, cs_n, mosi;
  spi_nor dut(.clk(clk), .rst_n(rst_n), .start(start), .op(op), .addr(addr), .len(len),
              .busy(busy), .done(done), .wdata(wdata), .wvalid(wvalid), .wready(wready),
              .rdata(rdata), .rvalid(rvalid), .rready(rready),
              .sck(sck), .cs_n(cs_n), .mosi(mosi), .miso(miso));
  initial begin
    $dumpfile("spi_tb.vcd");
    $dumpvars(0, spi_tb);
  end
endmodule
