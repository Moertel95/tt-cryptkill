# Standalone cocotb tests (Icarus Verilog). `make -C verify` runs every suite;
# `make -C verify TOP=xts sim` runs one.
SIM ?= icarus
TOPLEVEL_LANG ?= verilog
TOP ?= aes

ifeq ($(TOP),aes)
VERILOG_SOURCES += $(PWD)/../src/aes128.v $(PWD)/aes_tb.v
else ifeq ($(TOP),xts)
VERILOG_SOURCES += $(PWD)/../src/aes128.v $(PWD)/../src/xts128.v $(PWD)/xts_tb.v
endif
TOPLEVEL = $(TOP)_tb
MODULE = $(TOP)_test
SIM_BUILD = sim_build_$(TOP)
COCOTB_RESULTS_FILE = results_$(TOP).xml

# not `all`: cocotb's Makefile.sim also defines `all` and would run aes twice
.DEFAULT_GOAL := regress
.PHONY: regress
regress:
	rm -f results_*.xml
	$(MAKE) TOP=aes sim
	$(MAKE) TOP=xts sim
	# cocotb's make exits 0 on test failure; fail the build from the results
	! grep -l "<failure" results_*.xml

include $(shell cocotb-config --makefiles)/Makefile.sim
