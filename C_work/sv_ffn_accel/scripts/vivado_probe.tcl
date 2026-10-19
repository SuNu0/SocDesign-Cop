set script_dir [file dirname [file normalize [info script]]]
set out_dir [file normalize [file join $script_dir .. build vivado_probe]]
file mkdir $out_dir
puts "VIVADO_VERSION=[version -short]"
set all_parts [get_parts -quiet]
puts "INSTALLED_PART_COUNT=[llength $all_parts]"
puts "INSTALLED_PART_EXAMPLES=[lrange $all_parts 0 11]"
set candidates [get_parts -quiet xc7a100tcsg324-1]
if {[llength $candidates] == 0} {
  set candidates [get_parts -quiet xc7a100t*]
}
if {[llength $candidates] == 0} {
  set candidates [get_parts -quiet xc7a200t*]
}
if {[llength $candidates] == 0} {
  foreach pattern {xc7z020clg400-1 xc7z020* xc7s50* xczu3eg* xczu4ev* xczu7ev* xck26* xcau25p*} {
    set candidates [get_parts -quiet $pattern]
    if {[llength $candidates] > 0} {break}
  }
}
if {[llength $candidates] == 0 && [llength $all_parts] > 0} {
  set candidates [list [lindex $all_parts 0]]
}
if {[llength $candidates] == 0} {
  error "Vivado is installed but no target device definitions are available."
}
set chosen [lindex $candidates 0]
puts "SELECTED_PART=$chosen"
puts "MATCHING_PARTS=[llength $candidates]"
set fd [open [file join $out_dir selected_part.txt] w]
puts $fd $chosen
close $fd
foreach command {synth_design report_utilization report_timing_summary show_schematic write_schematic} {
  puts "COMMAND_$command=[llength [info commands $command]]"
}
puts "PROBE_PASS"
