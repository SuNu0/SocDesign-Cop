# Reproducible Vivado project-mode synthesis, preserving existing RTL hierarchy.
# Usage: vivado -mode batch -source vivado_hierarchy.tcl [-tclargs PART OUTPUT_DIR]
set script_dir [file dirname [file normalize [info script]]]
set root [file normalize [file join $script_dir ..]]
set part xc7z020clg400-1
if {[llength $argv] >= 1} {set part [lindex $argv 0]}
set out_dir [file normalize [file join $root build vivado_hierarchy]]
if {[llength $argv] >= 2} {set out_dir [file normalize [lindex $argv 1]]}
set project_dir [file join $out_dir project]
set report_dir [file join $out_dir reports]
if {[file exists [file join $project_dir ffn_accel_hierarchy.xpr]]} {
  error "Project already exists; choose a new OUTPUT_DIR to preserve the existing results: $project_dir"
}
if {[llength [get_parts -quiet $part]] == 0} {error "Target part is not installed: $part"}
file mkdir $report_dir
set_param general.maxThreads 4
create_project ffn_accel_hierarchy $project_dir -part $part
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
set sources [list [file join $root rtl ffn_numeric_pkg.sv] [file join $root rtl ffn_sram_1rw.sv] [file join $root rtl ffn_accel.sv]]
add_files -norecurse $sources
set_property file_type SystemVerilog [get_files *.sv]
set_property top ffn_accel [current_fileset]
update_compile_order -fileset sources_1
# Vivado accepts these clock / I/O SDC commands in an XDC file. Keep the RTL unchanged.
set xdc [file join $out_dir ffn_accel_vivado.xdc]
file copy [file join $root constraints ffn_accel.sdc] $xdc
add_files -fileset constrs_1 -norecurse $xdc
set_property STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY none [get_runs synth_1]
puts "SYNTHESIS_TARGET=$part"
puts "SYNTHESIS_HIERARCHY=none"
puts "SYNTHESIS_PROJECT=[file join $project_dir ffn_accel_hierarchy.xpr]"
launch_runs synth_1 -jobs 2
wait_on_run synth_1
set run_status [get_property STATUS [get_runs synth_1]]
puts "SYNTHESIS_RUN_STATUS=$run_status"
if {![string match "*Complete*" $run_status]} {
  error "Synthesis did not complete: $run_status. Inspect [file join $project_dir ffn_accel_hierarchy.runs synth_1 runme.log]"
}
open_run synth_1
write_checkpoint -force [file join $out_dir ffn_accel_synth.dcp]
write_verilog -force -mode funcsim [file join $out_dir ffn_accel_synth.v]
report_utilization -hierarchical -hierarchical_min_primitive_count 0 -file [file join $report_dir utilization_hierarchical.rpt]
report_utilization -file [file join $report_dir utilization.rpt]
report_timing_summary -file [file join $report_dir timing_summary_post_synth.rpt]
set fd [open [file join $report_dir hierarchy.tsv] w]
puts $fd "instance\tref_name\torig_ref_name"
foreach cell [lsort [get_cells -hierarchical -filter {IS_PRIMITIVE == 0}]] {
  set original [get_property -quiet ORIG_REF_NAME $cell]
  puts $fd "[get_property NAME $cell]\t[get_property REF_NAME $cell]\t$original"
}
close $fd
set fd [open [file join $report_dir primitives.tsv] w]
puts $fd "ref_name\tcount"
array set counts {}
foreach cell [get_cells -hierarchical -filter {IS_PRIMITIVE == 1}] {
  set ref [get_property REF_NAME $cell]
  if {![info exists counts($ref)]} {set counts($ref) 0}
  incr counts($ref)
}
foreach ref [lsort [array names counts]] {puts $fd "$ref\t$counts($ref)"}
close $fd
set fd [open [file join $report_dir synthesis_summary.txt] w]
puts $fd "Vivado: [version -short]"
puts $fd "Part: $part"
puts $fd "Top: ffn_accel"
puts $fd "Flatten hierarchy: none"
puts $fd "Run status: $run_status"
puts $fd "Hierarchical cells: [llength [get_cells -hierarchical -filter {IS_PRIMITIVE == 0}]]"
puts $fd "Primitive cells: [llength [get_cells -hierarchical -filter {IS_PRIMITIVE == 1}]]"
puts $fd "Clock target: 6.666667 ns (150 MHz)"
puts $fd "Stage: post-synthesis; no placement or routing performed"
close $fd
puts "VIVADO_HIERARCHY_SYNTHESIS_PASS"
close_project
