// aes128.v -- AES-128 iterative core, encrypt + decrypt, on-the-fly key schedule
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

  function automatic [7:0] sb; input [7:0] a; begin case(a)
    8'h00:sb=8'h63; 8'h01:sb=8'h7c; 8'h02:sb=8'h77; 8'h03:sb=8'h7b; 8'h04:sb=8'hf2; 8'h05:sb=8'h6b; 8'h06:sb=8'h6f; 8'h07:sb=8'hc5;
    8'h08:sb=8'h30; 8'h09:sb=8'h01; 8'h0a:sb=8'h67; 8'h0b:sb=8'h2b; 8'h0c:sb=8'hfe; 8'h0d:sb=8'hd7; 8'h0e:sb=8'hab; 8'h0f:sb=8'h76;
    8'h10:sb=8'hca; 8'h11:sb=8'h82; 8'h12:sb=8'hc9; 8'h13:sb=8'h7d; 8'h14:sb=8'hfa; 8'h15:sb=8'h59; 8'h16:sb=8'h47; 8'h17:sb=8'hf0;
    8'h18:sb=8'had; 8'h19:sb=8'hd4; 8'h1a:sb=8'ha2; 8'h1b:sb=8'haf; 8'h1c:sb=8'h9c; 8'h1d:sb=8'ha4; 8'h1e:sb=8'h72; 8'h1f:sb=8'hc0;
    8'h20:sb=8'hb7; 8'h21:sb=8'hfd; 8'h22:sb=8'h93; 8'h23:sb=8'h26; 8'h24:sb=8'h36; 8'h25:sb=8'h3f; 8'h26:sb=8'hf7; 8'h27:sb=8'hcc;
    8'h28:sb=8'h34; 8'h29:sb=8'ha5; 8'h2a:sb=8'he5; 8'h2b:sb=8'hf1; 8'h2c:sb=8'h71; 8'h2d:sb=8'hd8; 8'h2e:sb=8'h31; 8'h2f:sb=8'h15;
    8'h30:sb=8'h04; 8'h31:sb=8'hc7; 8'h32:sb=8'h23; 8'h33:sb=8'hc3; 8'h34:sb=8'h18; 8'h35:sb=8'h96; 8'h36:sb=8'h05; 8'h37:sb=8'h9a;
    8'h38:sb=8'h07; 8'h39:sb=8'h12; 8'h3a:sb=8'h80; 8'h3b:sb=8'he2; 8'h3c:sb=8'heb; 8'h3d:sb=8'h27; 8'h3e:sb=8'hb2; 8'h3f:sb=8'h75;
    8'h40:sb=8'h09; 8'h41:sb=8'h83; 8'h42:sb=8'h2c; 8'h43:sb=8'h1a; 8'h44:sb=8'h1b; 8'h45:sb=8'h6e; 8'h46:sb=8'h5a; 8'h47:sb=8'ha0;
    8'h48:sb=8'h52; 8'h49:sb=8'h3b; 8'h4a:sb=8'hd6; 8'h4b:sb=8'hb3; 8'h4c:sb=8'h29; 8'h4d:sb=8'he3; 8'h4e:sb=8'h2f; 8'h4f:sb=8'h84;
    8'h50:sb=8'h53; 8'h51:sb=8'hd1; 8'h52:sb=8'h00; 8'h53:sb=8'hed; 8'h54:sb=8'h20; 8'h55:sb=8'hfc; 8'h56:sb=8'hb1; 8'h57:sb=8'h5b;
    8'h58:sb=8'h6a; 8'h59:sb=8'hcb; 8'h5a:sb=8'hbe; 8'h5b:sb=8'h39; 8'h5c:sb=8'h4a; 8'h5d:sb=8'h4c; 8'h5e:sb=8'h58; 8'h5f:sb=8'hcf;
    8'h60:sb=8'hd0; 8'h61:sb=8'hef; 8'h62:sb=8'haa; 8'h63:sb=8'hfb; 8'h64:sb=8'h43; 8'h65:sb=8'h4d; 8'h66:sb=8'h33; 8'h67:sb=8'h85;
    8'h68:sb=8'h45; 8'h69:sb=8'hf9; 8'h6a:sb=8'h02; 8'h6b:sb=8'h7f; 8'h6c:sb=8'h50; 8'h6d:sb=8'h3c; 8'h6e:sb=8'h9f; 8'h6f:sb=8'ha8;
    8'h70:sb=8'h51; 8'h71:sb=8'ha3; 8'h72:sb=8'h40; 8'h73:sb=8'h8f; 8'h74:sb=8'h92; 8'h75:sb=8'h9d; 8'h76:sb=8'h38; 8'h77:sb=8'hf5;
    8'h78:sb=8'hbc; 8'h79:sb=8'hb6; 8'h7a:sb=8'hda; 8'h7b:sb=8'h21; 8'h7c:sb=8'h10; 8'h7d:sb=8'hff; 8'h7e:sb=8'hf3; 8'h7f:sb=8'hd2;
    8'h80:sb=8'hcd; 8'h81:sb=8'h0c; 8'h82:sb=8'h13; 8'h83:sb=8'hec; 8'h84:sb=8'h5f; 8'h85:sb=8'h97; 8'h86:sb=8'h44; 8'h87:sb=8'h17;
    8'h88:sb=8'hc4; 8'h89:sb=8'ha7; 8'h8a:sb=8'h7e; 8'h8b:sb=8'h3d; 8'h8c:sb=8'h64; 8'h8d:sb=8'h5d; 8'h8e:sb=8'h19; 8'h8f:sb=8'h73;
    8'h90:sb=8'h60; 8'h91:sb=8'h81; 8'h92:sb=8'h4f; 8'h93:sb=8'hdc; 8'h94:sb=8'h22; 8'h95:sb=8'h2a; 8'h96:sb=8'h90; 8'h97:sb=8'h88;
    8'h98:sb=8'h46; 8'h99:sb=8'hee; 8'h9a:sb=8'hb8; 8'h9b:sb=8'h14; 8'h9c:sb=8'hde; 8'h9d:sb=8'h5e; 8'h9e:sb=8'h0b; 8'h9f:sb=8'hdb;
    8'ha0:sb=8'he0; 8'ha1:sb=8'h32; 8'ha2:sb=8'h3a; 8'ha3:sb=8'h0a; 8'ha4:sb=8'h49; 8'ha5:sb=8'h06; 8'ha6:sb=8'h24; 8'ha7:sb=8'h5c;
    8'ha8:sb=8'hc2; 8'ha9:sb=8'hd3; 8'haa:sb=8'hac; 8'hab:sb=8'h62; 8'hac:sb=8'h91; 8'had:sb=8'h95; 8'hae:sb=8'he4; 8'haf:sb=8'h79;
    8'hb0:sb=8'he7; 8'hb1:sb=8'hc8; 8'hb2:sb=8'h37; 8'hb3:sb=8'h6d; 8'hb4:sb=8'h8d; 8'hb5:sb=8'hd5; 8'hb6:sb=8'h4e; 8'hb7:sb=8'ha9;
    8'hb8:sb=8'h6c; 8'hb9:sb=8'h56; 8'hba:sb=8'hf4; 8'hbb:sb=8'hea; 8'hbc:sb=8'h65; 8'hbd:sb=8'h7a; 8'hbe:sb=8'hae; 8'hbf:sb=8'h08;
    8'hc0:sb=8'hba; 8'hc1:sb=8'h78; 8'hc2:sb=8'h25; 8'hc3:sb=8'h2e; 8'hc4:sb=8'h1c; 8'hc5:sb=8'ha6; 8'hc6:sb=8'hb4; 8'hc7:sb=8'hc6;
    8'hc8:sb=8'he8; 8'hc9:sb=8'hdd; 8'hca:sb=8'h74; 8'hcb:sb=8'h1f; 8'hcc:sb=8'h4b; 8'hcd:sb=8'hbd; 8'hce:sb=8'h8b; 8'hcf:sb=8'h8a;
    8'hd0:sb=8'h70; 8'hd1:sb=8'h3e; 8'hd2:sb=8'hb5; 8'hd3:sb=8'h66; 8'hd4:sb=8'h48; 8'hd5:sb=8'h03; 8'hd6:sb=8'hf6; 8'hd7:sb=8'h0e;
    8'hd8:sb=8'h61; 8'hd9:sb=8'h35; 8'hda:sb=8'h57; 8'hdb:sb=8'hb9; 8'hdc:sb=8'h86; 8'hdd:sb=8'hc1; 8'hde:sb=8'h1d; 8'hdf:sb=8'h9e;
    8'he0:sb=8'he1; 8'he1:sb=8'hf8; 8'he2:sb=8'h98; 8'he3:sb=8'h11; 8'he4:sb=8'h69; 8'he5:sb=8'hd9; 8'he6:sb=8'h8e; 8'he7:sb=8'h94;
    8'he8:sb=8'h9b; 8'he9:sb=8'h1e; 8'hea:sb=8'h87; 8'heb:sb=8'he9; 8'hec:sb=8'hce; 8'hed:sb=8'h55; 8'hee:sb=8'h28; 8'hef:sb=8'hdf;
    8'hf0:sb=8'h8c; 8'hf1:sb=8'ha1; 8'hf2:sb=8'h89; 8'hf3:sb=8'h0d; 8'hf4:sb=8'hbf; 8'hf5:sb=8'he6; 8'hf6:sb=8'h42; 8'hf7:sb=8'h68;
    8'hf8:sb=8'h41; 8'hf9:sb=8'h99; 8'hfa:sb=8'h2d; 8'hfb:sb=8'h0f; 8'hfc:sb=8'hb0; 8'hfd:sb=8'h54; 8'hfe:sb=8'hbb; 8'hff:sb=8'h16;
    default: sb=8'h00; endcase end endfunction
  function automatic [7:0] isb; input [7:0] a; begin case(a)
    8'h00:isb=8'h52; 8'h01:isb=8'h09; 8'h02:isb=8'h6a; 8'h03:isb=8'hd5; 8'h04:isb=8'h30; 8'h05:isb=8'h36; 8'h06:isb=8'ha5; 8'h07:isb=8'h38;
    8'h08:isb=8'hbf; 8'h09:isb=8'h40; 8'h0a:isb=8'ha3; 8'h0b:isb=8'h9e; 8'h0c:isb=8'h81; 8'h0d:isb=8'hf3; 8'h0e:isb=8'hd7; 8'h0f:isb=8'hfb;
    8'h10:isb=8'h7c; 8'h11:isb=8'he3; 8'h12:isb=8'h39; 8'h13:isb=8'h82; 8'h14:isb=8'h9b; 8'h15:isb=8'h2f; 8'h16:isb=8'hff; 8'h17:isb=8'h87;
    8'h18:isb=8'h34; 8'h19:isb=8'h8e; 8'h1a:isb=8'h43; 8'h1b:isb=8'h44; 8'h1c:isb=8'hc4; 8'h1d:isb=8'hde; 8'h1e:isb=8'he9; 8'h1f:isb=8'hcb;
    8'h20:isb=8'h54; 8'h21:isb=8'h7b; 8'h22:isb=8'h94; 8'h23:isb=8'h32; 8'h24:isb=8'ha6; 8'h25:isb=8'hc2; 8'h26:isb=8'h23; 8'h27:isb=8'h3d;
    8'h28:isb=8'hee; 8'h29:isb=8'h4c; 8'h2a:isb=8'h95; 8'h2b:isb=8'h0b; 8'h2c:isb=8'h42; 8'h2d:isb=8'hfa; 8'h2e:isb=8'hc3; 8'h2f:isb=8'h4e;
    8'h30:isb=8'h08; 8'h31:isb=8'h2e; 8'h32:isb=8'ha1; 8'h33:isb=8'h66; 8'h34:isb=8'h28; 8'h35:isb=8'hd9; 8'h36:isb=8'h24; 8'h37:isb=8'hb2;
    8'h38:isb=8'h76; 8'h39:isb=8'h5b; 8'h3a:isb=8'ha2; 8'h3b:isb=8'h49; 8'h3c:isb=8'h6d; 8'h3d:isb=8'h8b; 8'h3e:isb=8'hd1; 8'h3f:isb=8'h25;
    8'h40:isb=8'h72; 8'h41:isb=8'hf8; 8'h42:isb=8'hf6; 8'h43:isb=8'h64; 8'h44:isb=8'h86; 8'h45:isb=8'h68; 8'h46:isb=8'h98; 8'h47:isb=8'h16;
    8'h48:isb=8'hd4; 8'h49:isb=8'ha4; 8'h4a:isb=8'h5c; 8'h4b:isb=8'hcc; 8'h4c:isb=8'h5d; 8'h4d:isb=8'h65; 8'h4e:isb=8'hb6; 8'h4f:isb=8'h92;
    8'h50:isb=8'h6c; 8'h51:isb=8'h70; 8'h52:isb=8'h48; 8'h53:isb=8'h50; 8'h54:isb=8'hfd; 8'h55:isb=8'hed; 8'h56:isb=8'hb9; 8'h57:isb=8'hda;
    8'h58:isb=8'h5e; 8'h59:isb=8'h15; 8'h5a:isb=8'h46; 8'h5b:isb=8'h57; 8'h5c:isb=8'ha7; 8'h5d:isb=8'h8d; 8'h5e:isb=8'h9d; 8'h5f:isb=8'h84;
    8'h60:isb=8'h90; 8'h61:isb=8'hd8; 8'h62:isb=8'hab; 8'h63:isb=8'h00; 8'h64:isb=8'h8c; 8'h65:isb=8'hbc; 8'h66:isb=8'hd3; 8'h67:isb=8'h0a;
    8'h68:isb=8'hf7; 8'h69:isb=8'he4; 8'h6a:isb=8'h58; 8'h6b:isb=8'h05; 8'h6c:isb=8'hb8; 8'h6d:isb=8'hb3; 8'h6e:isb=8'h45; 8'h6f:isb=8'h06;
    8'h70:isb=8'hd0; 8'h71:isb=8'h2c; 8'h72:isb=8'h1e; 8'h73:isb=8'h8f; 8'h74:isb=8'hca; 8'h75:isb=8'h3f; 8'h76:isb=8'h0f; 8'h77:isb=8'h02;
    8'h78:isb=8'hc1; 8'h79:isb=8'haf; 8'h7a:isb=8'hbd; 8'h7b:isb=8'h03; 8'h7c:isb=8'h01; 8'h7d:isb=8'h13; 8'h7e:isb=8'h8a; 8'h7f:isb=8'h6b;
    8'h80:isb=8'h3a; 8'h81:isb=8'h91; 8'h82:isb=8'h11; 8'h83:isb=8'h41; 8'h84:isb=8'h4f; 8'h85:isb=8'h67; 8'h86:isb=8'hdc; 8'h87:isb=8'hea;
    8'h88:isb=8'h97; 8'h89:isb=8'hf2; 8'h8a:isb=8'hcf; 8'h8b:isb=8'hce; 8'h8c:isb=8'hf0; 8'h8d:isb=8'hb4; 8'h8e:isb=8'he6; 8'h8f:isb=8'h73;
    8'h90:isb=8'h96; 8'h91:isb=8'hac; 8'h92:isb=8'h74; 8'h93:isb=8'h22; 8'h94:isb=8'he7; 8'h95:isb=8'had; 8'h96:isb=8'h35; 8'h97:isb=8'h85;
    8'h98:isb=8'he2; 8'h99:isb=8'hf9; 8'h9a:isb=8'h37; 8'h9b:isb=8'he8; 8'h9c:isb=8'h1c; 8'h9d:isb=8'h75; 8'h9e:isb=8'hdf; 8'h9f:isb=8'h6e;
    8'ha0:isb=8'h47; 8'ha1:isb=8'hf1; 8'ha2:isb=8'h1a; 8'ha3:isb=8'h71; 8'ha4:isb=8'h1d; 8'ha5:isb=8'h29; 8'ha6:isb=8'hc5; 8'ha7:isb=8'h89;
    8'ha8:isb=8'h6f; 8'ha9:isb=8'hb7; 8'haa:isb=8'h62; 8'hab:isb=8'h0e; 8'hac:isb=8'haa; 8'had:isb=8'h18; 8'hae:isb=8'hbe; 8'haf:isb=8'h1b;
    8'hb0:isb=8'hfc; 8'hb1:isb=8'h56; 8'hb2:isb=8'h3e; 8'hb3:isb=8'h4b; 8'hb4:isb=8'hc6; 8'hb5:isb=8'hd2; 8'hb6:isb=8'h79; 8'hb7:isb=8'h20;
    8'hb8:isb=8'h9a; 8'hb9:isb=8'hdb; 8'hba:isb=8'hc0; 8'hbb:isb=8'hfe; 8'hbc:isb=8'h78; 8'hbd:isb=8'hcd; 8'hbe:isb=8'h5a; 8'hbf:isb=8'hf4;
    8'hc0:isb=8'h1f; 8'hc1:isb=8'hdd; 8'hc2:isb=8'ha8; 8'hc3:isb=8'h33; 8'hc4:isb=8'h88; 8'hc5:isb=8'h07; 8'hc6:isb=8'hc7; 8'hc7:isb=8'h31;
    8'hc8:isb=8'hb1; 8'hc9:isb=8'h12; 8'hca:isb=8'h10; 8'hcb:isb=8'h59; 8'hcc:isb=8'h27; 8'hcd:isb=8'h80; 8'hce:isb=8'hec; 8'hcf:isb=8'h5f;
    8'hd0:isb=8'h60; 8'hd1:isb=8'h51; 8'hd2:isb=8'h7f; 8'hd3:isb=8'ha9; 8'hd4:isb=8'h19; 8'hd5:isb=8'hb5; 8'hd6:isb=8'h4a; 8'hd7:isb=8'h0d;
    8'hd8:isb=8'h2d; 8'hd9:isb=8'he5; 8'hda:isb=8'h7a; 8'hdb:isb=8'h9f; 8'hdc:isb=8'h93; 8'hdd:isb=8'hc9; 8'hde:isb=8'h9c; 8'hdf:isb=8'hef;
    8'he0:isb=8'ha0; 8'he1:isb=8'he0; 8'he2:isb=8'h3b; 8'he3:isb=8'h4d; 8'he4:isb=8'hae; 8'he5:isb=8'h2a; 8'he6:isb=8'hf5; 8'he7:isb=8'hb0;
    8'he8:isb=8'hc8; 8'he9:isb=8'heb; 8'hea:isb=8'hbb; 8'heb:isb=8'h3c; 8'hec:isb=8'h83; 8'hed:isb=8'h53; 8'hee:isb=8'h99; 8'hef:isb=8'h61;
    8'hf0:isb=8'h17; 8'hf1:isb=8'h2b; 8'hf2:isb=8'h04; 8'hf3:isb=8'h7e; 8'hf4:isb=8'hba; 8'hf5:isb=8'h77; 8'hf6:isb=8'hd6; 8'hf7:isb=8'h26;
    8'hf8:isb=8'he1; 8'hf9:isb=8'h69; 8'hfa:isb=8'h14; 8'hfb:isb=8'h63; 8'hfc:isb=8'h55; 8'hfd:isb=8'h21; 8'hfe:isb=8'h0c; 8'hff:isb=8'h7d;
    default: isb=8'h00; endcase end endfunction
  function automatic [127:0] srows; input [127:0] s; reg [127:0] y; begin
    y[120 +: 8] = s[120 +: 8];
    y[112 +: 8] = s[80 +: 8];
    y[104 +: 8] = s[40 +: 8];
    y[96 +: 8] = s[0 +: 8];
    y[88 +: 8] = s[88 +: 8];
    y[80 +: 8] = s[48 +: 8];
    y[72 +: 8] = s[8 +: 8];
    y[64 +: 8] = s[96 +: 8];
    y[56 +: 8] = s[56 +: 8];
    y[48 +: 8] = s[16 +: 8];
    y[40 +: 8] = s[104 +: 8];
    y[32 +: 8] = s[64 +: 8];
    y[24 +: 8] = s[24 +: 8];
    y[16 +: 8] = s[112 +: 8];
    y[8 +: 8] = s[72 +: 8];
    y[0 +: 8] = s[32 +: 8];
    srows = y; end endfunction
  function automatic [127:0] inv_srows; input [127:0] s; reg [127:0] y; begin
    y[120 +: 8] = s[120 +: 8];
    y[112 +: 8] = s[16 +: 8];
    y[104 +: 8] = s[40 +: 8];
    y[96 +: 8] = s[64 +: 8];
    y[88 +: 8] = s[88 +: 8];
    y[80 +: 8] = s[112 +: 8];
    y[72 +: 8] = s[8 +: 8];
    y[64 +: 8] = s[32 +: 8];
    y[56 +: 8] = s[56 +: 8];
    y[48 +: 8] = s[80 +: 8];
    y[40 +: 8] = s[104 +: 8];
    y[32 +: 8] = s[0 +: 8];
    y[24 +: 8] = s[24 +: 8];
    y[16 +: 8] = s[48 +: 8];
    y[8 +: 8] = s[72 +: 8];
    y[0 +: 8] = s[96 +: 8];
    inv_srows = y; end endfunction

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


  function automatic [127:0] enc_round; input [127:0] s; input [127:0] k; input last; reg [127:0] a,b,c; begin
    a = {sb(s[120 +: 8]), sb(s[112 +: 8]), sb(s[104 +: 8]), sb(s[96 +: 8]), sb(s[88 +: 8]), sb(s[80 +: 8]), sb(s[72 +: 8]), sb(s[64 +: 8]), sb(s[56 +: 8]), sb(s[48 +: 8]), sb(s[40 +: 8]), sb(s[32 +: 8]), sb(s[24 +: 8]), sb(s[16 +: 8]), sb(s[8 +: 8]), sb(s[0 +: 8])};
    b = srows(a);
    c = last ? b : mixcols(b);
    enc_round = c ^ k;
  end endfunction
  function automatic [127:0] dec_round; input [127:0] s; input [127:0] k; input last; reg [127:0] a,b,c; begin
    a = inv_srows(s);
    b = {isb(a[120 +: 8]), isb(a[112 +: 8]), isb(a[104 +: 8]), isb(a[96 +: 8]), isb(a[88 +: 8]), isb(a[80 +: 8]), isb(a[72 +: 8]), isb(a[64 +: 8]), isb(a[56 +: 8]), isb(a[48 +: 8]), isb(a[40 +: 8]), isb(a[32 +: 8]), isb(a[24 +: 8]), isb(a[16 +: 8]), isb(a[8 +: 8]), isb(a[0 +: 8])};
    c = b ^ k;
    dec_round = last ? c : invmixcols(c);
  end endfunction


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

