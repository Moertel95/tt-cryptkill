#!/usr/bin/env bash
# Mutation check: every mutant must be killed, either by a failing test or by the
# wall-clock limit (a sim that hangs, e.g. a zero-delay loop where sim time never
# advances, counts as killed instead of blocking the batch).
# Usage (repo root): verify/mutate.sh [name-regex]   env: LIMIT=seconds (default 180)
# Needs the cocotb of the suite it runs: verify/ = cocotb 1.9, test/ (T*) = cocotb 2.
set -u
cd "$(dirname "$0")/.."
LIMIT=${LIMIT:-180}; PAT=${1:-.}
BK=$(mktemp -d); cp src/*.v "$BK"/
trap 'cp "$BK"/*.v src/; rm -rf "$BK"' EXIT   # sources restored even on Ctrl-C
bad=0

mut() {  # name file perl-substitution dir [make args]
  local name=$1 file=$2 expr=$3 dir=$4 lim=$LIMIT rc; shift 4
  [[ $name =~ $PAT ]] || return 0
  [[ $* == *spi* ]] && lim=$((LIMIT * 2))  # spi_random alone is ~110 s wall
  cp "$BK"/*.v src/; perl -0pi -e "$expr" "src/$file"
  if cmp -s "$BK/$file" "src/$file"; then echo "$name: NOT APPLIED"; bad=$((bad + 1)); return; fi
  rm -f "$dir"/results*.xml
  (cd "$dir" && timeout -k 10 "$lim" make "$@") > "$BK/log" 2>&1; rc=$?
  if [[ $rc == 124 || $rc == 137 ]]; then echo "$name: KILLED (wall-clock ${lim}s)"
  elif grep -qs "<failure" "$dir"/results*.xml; then
    echo "$name: KILLED $(grep -m1 -oE '(AssertionError|SimTimeoutError)[^\"]{0,80}' "$BK/log")"
  elif ls "$dir"/results*.xml >/dev/null 2>&1; then echo "$name: SURVIVED"; bad=$((bad + 1))
  else echo "$name: ERROR rc=$rc (no results; build failed?)"; tail -5 "$BK/log"; bad=$((bad + 1)); fi
}

X='verify TOP=xts sim'
# XTS: block 0 must use the freshly committed tweak (T_new bypass)
mut X0_blk0_stale_T  xts128.v 's/: T_new;/: T;/'                     $X
# crypto-erase: every secret register cleared, tamper honoured
mut E1_key1_kept     xts128.v 's/key1 <= 0; //'                      $X
mut E2_key2_kept     xts128.v 's/key2 <= 0; //'                      $X
mut E3_T_kept        xts128.v 's/ T <= 0;//'                         $X
mut E4_core_rst_n    xts128.v 's/\.rst_n\(rst_e\)/.rst_n(rst_n)/'    $X
mut E5_rk_kept       aes128.v 's/ rk<=0;//'                          $X
mut E6_st_kept       aes128.v 's/st<=0; //'                          $X
mut E7_dout_kept     aes128.v 's/ dout<=0;//'                        $X
mut E8_no_tamper     xts128.v 's/rst_n & ~tsync\[1\]/rst_n/'         $X
# AES core
mut A1_no_start_edge aes128.v 's/start & ~start_d & ~busy/start & ~busy/' verify TOP=aes sim
# SPI-NOR master
S='verify TOP=spi sim'
mut S1_cs_gap_1clk   spi_nor.v 's/gap <= 3.d7;/gap <= 3'"'"'d0;/'    $S
mut S2_no_wren       spi_nor.v 's/\? G_WREN : G_END/? G_MAIN : G_END/' $S
mut S3_ignore_wip    spi_nor.v 's/if \(rx\[0\]\)/if (1'"'"'b0)/'     $S
mut S4_addr_order    spi_nor.v 's/\{opc, addr_q\}/{opc, addr_q[7:0], addr_q[15:8], addr_q[23:16]}/' $S
mut S5_no_rvalid     spi_nor.v 's/if \(!rvalid\) begin send/if (1'"'"'b1) begin send/' $S
# top: host protocol and erase domain (pin-level e2e, cocotb 2)
T=tt_um_cryptkill.v
mut T1_keywr_any_state $T 's/\.key_wr\(take & \(st == S_KEY\) & ~cmd\)/.key_wr(take \& ~cmd)/' test
mut T2_loadkey_keeps_sec $T 's/8.h01: begin key_ok <= 0; sec_ok <= 0;/8'"'"'h01: begin key_ok <= 0;/' test
mut T3_top_not_erased $T 's/always \@\(posedge clk or negedge rst_e\)/always @(posedge clk or negedge rst_n)/; s/if \(!rst_e\) begin\n      st <= S_IDLE/if (!rst_n) begin\n      st <= S_IDLE/' test
mut T4_spi_not_erased $T 's/\.rst_n\(rst_e\), \.start\(spi_go\)/.rst_n(rst_n), .start(spi_go)/' test
mut T5_no_block_addr $T 's/\{sector, j\[4:0\], 4.b0\}/{sector, 9'"'"'b0}/' test
mut T6_no_full_check $T 's/8.h03: if \(sec_ok & ~j\[5\]\)/8'"'"'h03: if (sec_ok)/' test
mut T7_ack_sticky    $T 's/if \(!vs\) ack <= 1.b0;/if (1==0) ack <= 1'"'"'b0;/' test
mut T8_no_tamper     $T 's/\.tamper\(uio_in\[7\]\)/.tamper(1'"'"'b0)/' test
mut T9_out_15        $T 's/if \(cnt == 5.d15\) st <= S_IDLE;/if (cnt == 5'"'"'d14) st <= S_IDLE;/' test
mut T10_setsec_nokey $T 's/8.h02: if \(key_ok\)/8'"'"'h02: if (1)/' test

echo "not killed: $bad"
exit $((bad > 0))
