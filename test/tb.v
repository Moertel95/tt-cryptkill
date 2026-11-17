`default_nettype none
`timescale 1ns / 1ps

/* This testbench just instantiates the module and makes some convenient wires
   that can be driven / tested by the cocotb test.py.
*/
module tb ();

  // Dump the signals to a FST file. You can view it with gtkwave or surfer.
  initial begin
    $dumpfile("tb.fst");
    $dumpvars(0, tb);
    #1;
  end

  // Wire up the inputs and outputs:
  reg clk;
  reg rst_n;
  reg ena;
  reg [7:0] ui_in;
  // uio inputs: 3 MISO (driven by the flash model), 4 HOST_VALID, 5 HOST_CMD, 7 TAMPER
  reg miso, host_valid, host_cmd, tamper;
  wire [7:0] uio_in = {tamper, 1'b0, host_cmd, host_valid, miso, 3'b0};
  wire [7:0] uo_out;
  wire [7:0] uio_out;
  wire [7:0] uio_oe;
  wire cs_n = uio_out[0], sck = uio_out[1], mosi = uio_out[2], ack = uio_out[6];
`ifdef GL_TEST
  wire VPWR = 1'b1;
  wire VGND = 1'b0;
`endif

  tt_um_cryptkill user_project (

      // Include power ports for the Gate Level test:
`ifdef GL_TEST
      .VPWR(VPWR),
      .VGND(VGND),
`endif

      .ui_in  (ui_in),    // Dedicated inputs
      .uo_out (uo_out),   // Dedicated outputs
      .uio_in (uio_in),   // IOs: Input path
      .uio_out(uio_out),  // IOs: Output path
      .uio_oe (uio_oe),   // IOs: Enable path (active high: 0=input, 1=output)
      .ena    (ena),      // enable - goes high when design is selected
      .clk    (clk),      // clock
      .rst_n  (rst_n)     // not reset
  );

endmodule
