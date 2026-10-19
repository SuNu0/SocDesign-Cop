# Constraint template, not a claim of closed timing. Replace interface budgets
# with platform values and link the actual standard-cell/SRAM timing libraries.
create_clock -name sys_clk -period 6.666667 [get_ports clk]
set_clock_uncertainty 0.100 [get_clocks sys_clk]
set_input_delay 1.000 -clock sys_clk [get_ports {i_icb_cmd_valid i_icb_cmd_read i_icb_cmd_addr[*] i_icb_cmd_wdata[*] i_icb_cmd_wmask[*] i_icb_rsp_ready}]
set_output_delay 1.000 -clock sys_clk [get_ports {o_icb_cmd_ready o_icb_rsp_valid o_icb_rsp_rdata[*] o_icb_rsp_err o_irq}]
# rst_n is asynchronous. Reset recovery/removal and release synchronization must
# be checked with the SoC reset methodology; no blanket false-path exceptions.
