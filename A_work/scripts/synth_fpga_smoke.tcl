# A synthesizability smoke test ONLY. This is NOT the contest ASIC flow.
set root [file normalize [file join [file dirname [info script]] ..]]
set out [file normalize [lindex $argv 0]]
file mkdir $out
create_project -in_memory -part xc7z020clg400-1
read_verilog -sv [glob [file join $root rtl compute *.sv]]
synth_design -top compute_lane -mode out_of_context -part xc7z020clg400-1
create_clock -name clk -period 6.666667 [get_ports clk]
report_utilization -file [file join $out utilization_fpga_only.rpt]
report_timing_summary -file [file join $out timing_fpga_only.rpt]
report_drc -file [file join $out drc_fpga_only.rpt]
write_checkpoint -force [file join $out compute_lane_fpga_only.dcp]
puts "A_FPGA_SYNTHESIZABILITY_SMOKE_PASSED_NOT_ASIC_SIGNOFF"
exit
