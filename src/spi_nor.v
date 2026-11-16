// spi_nor.v -- SPI-NOR (W25Q-class) master. Single-bit SPI mode 0, SCK = clk/2.
// MOSI changes on SCK falling, MISO is sampled on the clk edge that raises SCK.
//
// Ops (start is edge-gated, accepted only when idle; op/addr/len latched):
//   0 READ    : 03 A2 A1 A0, then len bytes out on rdata/rvalid (len=0: header only)
//   1 PROGRAM : 06 | 02 A2 A1 A0 + len bytes from wdata | 05 poll until WIP=0
//               (len=0: no flash traffic). Caller keeps addr..addr+len-1 in one
//               256-byte page -- the flash wraps inside the page otherwise.
//   2 ERASE4K : 06 | 20 A2 A1 A0 | 05 poll until WIP=0
//   3         : no-op, just done
// Streams: wready pulses the cycle AFTER wdata was taken (hold wdata/wvalid until
// then; the next byte is not sampled for 16 clk). Master waits for wvalid;
// rdata/rvalid held until rready. While waiting the master parks SCK low, CS low.
// CS stays high >= 9 clk between commands (W25Q tSHSL2 = 50 ns).
// shortcut: WIP poll has no timeout (dead/missing flash => busy forever until reset).
`default_nettype none

module spi_nor (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        start,
    input  wire [1:0]  op,
    input  wire [23:0] addr,
    input  wire [11:0] len,
    output wire        busy,
    output reg         done,
    input  wire [7:0]  wdata,
    input  wire        wvalid,
    output reg         wready,
    output reg  [7:0]  rdata,
    output reg         rvalid,
    input  wire        rready,
    output reg         sck,
    output reg         cs_n,
    output wire        mosi,
    input  wire        miso
);
  localparam OP_READ = 2'd0, OP_PROG = 2'd1, OP_ERASE = 2'd2;
  localparam S_IDLE = 2'd0, S_XFER = 2'd1, S_GAP = 2'd2;
  localparam G_WREN = 2'd0, G_MAIN = 2'd1, G_POLL = 2'd2, G_END = 2'd3;   // CS windows
  localparam P_NONE = 2'd0, P_RD = 2'd1, P_ST = 2'd2;                     // byte in flight

  reg [1:0]  state, seg, pend, op_q;
  reg [23:0] addr_q;
  reg [11:0] dcnt;
  reg [2:0]  hcnt, gap, bitn;
  reg [7:0]  sh, rx;
  reg        ph, bact, start_d;

  assign mosi = sh[7];
  assign busy = (state != S_IDLE);

  wire [7:0] opc = (op_q == OP_READ) ? 8'h03 : (op_q == OP_PROG) ? 8'h02 : 8'h20;
  // header byte picked from latched op/addr by hcnt (no 32-bit header register)
  wire [7:0] hbyte = (seg == G_WREN) ? 8'h06 : (seg == G_POLL) ? 8'h05 :
                     (hcnt == 3'd4) ? opc : (hcnt == 3'd3) ? addr_q[23:16] :
                     (hcnt == 3'd2) ? addr_q[15:8] : addr_q[7:0];

  task send(input [7:0] b); begin
    sh <= b; bitn <= 3'd7; ph <= 1'b0; bact <= 1'b1; end endtask

  task end_txn; begin
    cs_n <= 1'b1; gap <= 3'd7; state <= S_GAP;
    seg  <= (seg == G_WREN) ? G_MAIN : (seg == G_MAIN && op_q != OP_READ) ? G_POLL : G_END;
  end endtask

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      state <= S_IDLE; seg <= G_END; pend <= P_NONE; op_q <= 0; addr_q <= 0; dcnt <= 0;
      hcnt <= 0; gap <= 0; bitn <= 0; sh <= 0; rx <= 0; ph <= 0; bact <= 0;
      start_d <= 0; done <= 0; wready <= 0; rdata <= 0; rvalid <= 0; sck <= 0; cs_n <= 1'b1;
    end else begin
      done <= 1'b0; wready <= 1'b0; start_d <= start;
      if (rvalid & rready) rvalid <= 1'b0;

      // byte engine: 2 clk per bit
      if (bact) begin
        if (!ph) begin rx <= {rx[6:0], miso}; sck <= 1'b1; ph <= 1'b1; end
        else begin
          sck <= 1'b0; ph <= 1'b0;
          if (bitn == 3'd0) bact <= 1'b0;
          else begin sh <= {sh[6:0], 1'b0}; bitn <= bitn - 3'd1; end
        end
      end

      case (state)
        S_IDLE: if (start & ~start_d) begin
          op_q <= op; addr_q <= addr; dcnt <= len; gap <= 3'd0; state <= S_GAP;
          seg  <= (op == OP_READ) ? G_MAIN :
                  (op == OP_ERASE || (op == OP_PROG && len != 12'd0)) ? G_WREN : G_END;
        end
        S_GAP: if (gap != 3'd0) gap <= gap - 3'd1;
          else if (seg == G_END) begin done <= 1'b1; state <= S_IDLE; end
          else begin
            cs_n <= 1'b0; state <= S_XFER;
            hcnt <= (seg == G_MAIN) ? 3'd4 : 3'd1;
          end
        S_XFER: if (!bact) begin
          pend <= P_NONE;
          if (pend == P_RD) begin rdata <= rx; rvalid <= 1'b1; end
          else if (pend == P_ST) begin
            if (rx[0]) begin send(8'h00); pend <= P_ST; end   // WIP still set: keep reading SR1
            else end_txn;
          end
          else if (hcnt != 3'd0) begin
            send(hbyte); hcnt <= hcnt - 3'd1;
          end
          else case (seg)
            G_MAIN:
              if (dcnt == 12'd0 || op_q == OP_ERASE) end_txn;
              else if (op_q == OP_READ) begin
                if (!rvalid) begin send(8'h00); pend <= P_RD; dcnt <= dcnt - 12'd1; end
              end
              else if (wvalid) begin send(wdata); wready <= 1'b1; dcnt <= dcnt - 12'd1; end
            G_POLL:  begin send(8'h00); pend <= P_ST; end
            default: end_txn;   // G_WREN: opcode only
          endcase
        end
        default: state <= S_IDLE;
      endcase
    end
  end
endmodule
`default_nettype wire
