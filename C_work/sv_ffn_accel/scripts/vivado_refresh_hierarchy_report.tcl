set root [file normalize [file join [file dirname [info script]] ..]]
set out_dir [file join $root build vivado_hierarchy]
open_checkpoint [file join $out_dir ffn_accel_synth.dcp]
report_utilization -hierarchical -hierarchical_min_primitive_count 0 -file [file join $out_dir reports utilization_hierarchical.rpt]
puts "COMPLETE_HIERARCHY_REPORT_PASS"
close_design
