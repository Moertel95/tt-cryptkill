# Standalone cocotb test for the AES-128 core (Icarus Verilog).
SIM ?= icarus
TOPLEVEL_LANG ?= verilog
VERILOG_SOURCES += $(PWD)/../src/aes128.v $(PWD)/aes_tb.v
TOPLEVEL = aes_tb
MODULE = aes_test
include $(shell cocotb-config --makefiles)/Makefile.sim
