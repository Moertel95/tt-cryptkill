/*
 * Copyright (c) 2026 Moertel95
 * SPDX-License-Identifier: Apache-2.0
 *
 * tt_um_cryptkill -- AES-128-XTS self-encrypting SPI-NOR controller with
 * hardware crypto-erase. Host protocol (4-phase, one byte per handshake):
 *   host: put byte on ui[7:0] and host_cmd on uio[5], raise host_valid (uio[4]);
 *   chip: raises ACK (uio[6]) once the byte -- and any flash/AES work it starts --
 *         is finished; host drops host_valid; chip drops ACK. Next byte.
 * Commands (host_cmd=1), then their data bytes (host_cmd=0):
 *   01 LOAD_KEY   + 32 B (XTS key, key1 byte 0 first). Idle only; clears KEY_OK and
 *                 SEC_OK, so a mid-sector key change forces a new SET_SECTOR.
 *   02 SET_SECTOR + 2 B big-endian 15-bit sector n (bit 15 ignored); computes the
 *                 tweak, block index j=0. Needs KEY_OK. Flash address = n*512.
 *   03 WRITE_BLOCK+ 16 B plaintext -> encrypt block j, program flash n*512+16j, j++.
 *   04 READ_BLOCK : read + decrypt block j, j++; after ACK uo = plaintext byte 0,
 *                 each further handshake (byte ignored) shows the next byte; the
 *                 16th returns uo to status. Block ops need SEC_OK and j<32.
 *   05 ERASE      : erase the 4 KB flash sector holding sector n. Needs SEC_OK.
 * A rejected byte is still ACKed and sets ERR (cleared by the next command byte);
 * a command byte while data bytes are expected aborts the command (ERR).
 * uo (when not in READ_BLOCK output): {BUSY, 2'b0, ERASING, FULL(j=32), ERR, SEC_OK, KEY_OK}.
 * TAMPER (uio[7]): every register below except the input synchronizers sits in the
 * erase domain with xts128 (keys, tweak, AES core, block buffer, SPI master): all
 * cleared within 2 clk, any flash/host transaction in flight is dropped.
 */
`default_nettype none

module tt_um_cryptkill (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);
  localparam S_IDLE = 4'd0, S_KEY = 4'd1, S_SEC = 4'd2, S_TWK = 4'd3, S_WDAT = 4'd4,
             S_ENC = 4'd5, S_PROG = 4'd6, S_RD = 4'd7, S_DEC = 4'd8, S_OUT = 4'd9,
             S_ERASE = 4'd10;

  // host_valid synchronizer (not secret: outside the erase domain)
  reg [2:0] vsync;
  always @(posedge clk or negedge rst_n)
    if (!rst_n) vsync <= 3'b0; else vsync <= {vsync[1:0], uio_in[4]};
  wire vs  = vsync[1];
  wire cmd = uio_in[5];   // ui_in/host_cmd are stable while host_valid is high (protocol)

  reg  [3:0]   st;
  reg  [4:0]   cnt;
  reg  [5:0]   j;
  reg  [14:0]  sector;
  reg  [127:0] buf_q;
  reg          key_ok, sec_ok, err, ack, tw_go, blk_go, spi_go;

  wire take = vs & ~vsync[2] & ~ack &
              (st == S_IDLE || st == S_KEY || st == S_SEC || st == S_WDAT || st == S_OUT);

  wire [127:0] xdout;
  wire         xbusy, xdone, erasing;
  wire         rst_e = rst_n & ~erasing;

  xts128 xts (
    .clk(clk), .rst_n(rst_n), .tamper(uio_in[7]),
    .key_wr(take & (st == S_KEY) & ~cmd), .key_byte(ui_in), .erasing(erasing),
    .sector({113'b0, sector}), .tweak_start(tw_go), .blk_start(blk_go),
    .dec(st == S_DEC), .din(buf_q), .dout(xdout), .busy(xbusy), .done(xdone)
  );

  wire [7:0] dbyte = xdout[127 - 8*cnt[3:0] -: 8];
  wire [7:0] rdata;
  wire       rvalid, wready, sdone, sbusy, cs_n, sck, mosi;

  spi_nor flash (
    .clk(clk), .rst_n(rst_e), .start(spi_go),
    .op((st == S_PROG) ? 2'd1 : (st == S_RD) ? 2'd0 : 2'd2),
    .addr((st == S_ERASE) ? {sector, 9'b0} : {sector, j[4:0], 4'b0}),
    .len((st == S_ERASE) ? 12'd0 : 12'd16),
    .busy(sbusy), .done(sdone),
    .wdata(dbyte), .wvalid(st == S_PROG), .wready(wready),
    .rdata(rdata), .rvalid(rvalid), .rready(1'b1),
    .sck(sck), .cs_n(cs_n), .mosi(mosi), .miso(uio_in[3])
  );

  always @(posedge clk or negedge rst_e) begin
    if (!rst_e) begin
      st <= S_IDLE; cnt <= 0; j <= 0; sector <= 0; buf_q <= 0;
      key_ok <= 0; sec_ok <= 0; err <= 0; ack <= 0; tw_go <= 0; blk_go <= 0; spi_go <= 0;
    end else begin
      tw_go <= 1'b0; blk_go <= 1'b0; spi_go <= 1'b0;
      case (st)
        S_IDLE: if (take) begin
          ack <= 1'b1;
          if (!cmd) err <= 1'b1;   // data byte with no command
          else begin
            err <= 1'b0; cnt <= 0;
            case (ui_in)
              8'h01: begin key_ok <= 0; sec_ok <= 0; st <= S_KEY; end
              8'h02: if (key_ok) begin sec_ok <= 0; st <= S_SEC; end else err <= 1'b1;
              8'h03: if (sec_ok & ~j[5]) st <= S_WDAT; else err <= 1'b1;
              8'h04: if (sec_ok & ~j[5]) begin st <= S_RD;    spi_go <= 1'b1; ack <= 1'b0; end
                     else err <= 1'b1;
              8'h05: if (sec_ok)         begin st <= S_ERASE; spi_go <= 1'b1; ack <= 1'b0; end
                     else err <= 1'b1;
              default: err <= 1'b1;
            endcase
          end
        end
        S_KEY: if (take) begin   // xts128 shifts the byte in via key_wr
          ack <= 1'b1; cnt <= cnt + 5'd1;
          if (cmd) begin err <= 1'b1; st <= S_IDLE; end
          else if (cnt == 5'd31) begin key_ok <= 1'b1; st <= S_IDLE; end
        end
        S_SEC: if (take) begin
          cnt <= cnt + 5'd1;
          if (cmd) begin err <= 1'b1; ack <= 1'b1; st <= S_IDLE; end
          else begin
            sector <= {sector[6:0], ui_in};
            if (cnt[0]) begin tw_go <= 1'b1; st <= S_TWK; end else ack <= 1'b1;
          end
        end
        S_TWK: if (!tw_go && !xbusy) begin sec_ok <= 1'b1; j <= 0; ack <= 1'b1; st <= S_IDLE; end
        S_WDAT: if (take) begin
          cnt <= cnt + 5'd1;
          if (cmd) begin err <= 1'b1; ack <= 1'b1; st <= S_IDLE; end
          else begin
            buf_q <= {buf_q[119:0], ui_in};
            if (cnt == 5'd15) begin blk_go <= 1'b1; st <= S_ENC; end else ack <= 1'b1;
          end
        end
        S_ENC: if (xdone) begin cnt <= 0; spi_go <= 1'b1; st <= S_PROG; end
        S_PROG: begin
          if (wready) cnt <= cnt + 5'd1;
          if (sdone) begin j <= j + 6'd1; ack <= 1'b1; st <= S_IDLE; end
        end
        S_RD: begin
          if (rvalid) buf_q <= {buf_q[119:0], rdata};
          if (sdone) begin blk_go <= 1'b1; st <= S_DEC; end
        end
        S_DEC: if (xdone) begin cnt <= 0; j <= j + 6'd1; ack <= 1'b1; st <= S_OUT; end
        S_OUT: if (take) begin
          ack <= 1'b1; cnt <= cnt + 5'd1;
          if (cnt == 5'd15) st <= S_IDLE;
        end
        S_ERASE: if (sdone) begin ack <= 1'b1; st <= S_IDLE; end
        default: st <= S_IDLE;
      endcase
      if (!vs) ack <= 1'b0;   // 4-phase: ACK follows host_valid down
    end
  end

  assign uo_out  = (st == S_OUT) ? dbyte
                 : {st != S_IDLE, 2'b0, erasing, j[5], err, sec_ok, key_ok};
  assign uio_out = {1'b0, ack, 3'b0, mosi, sck, cs_n};
  assign uio_oe  = 8'b0100_0111;   // 0 CS_n, 1 SCK, 2 MOSI, 6 ACK out; 3 MISO, 4 VALID, 5 CMD, 7 TAMPER in

  wire _unused = &{ena, uio_in[6], uio_in[2:0], sbusy, 1'b0};
endmodule
`default_nettype wire
