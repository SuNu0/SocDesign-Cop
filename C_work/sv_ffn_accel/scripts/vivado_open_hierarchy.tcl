# Open the real synthesized design and export Vivado-native schematics.
# Launch in GUI mode: vivado -mode gui -source vivado_open_hierarchy.tcl
set script_dir [file dirname [file normalize [info script]]]
set root [file normalize [file join $script_dir ..]]
set out_dir [file join $root build vivado_hierarchy]
set project_file [file join $out_dir project ffn_accel_hierarchy.xpr]
set report_dir [file join $out_dir reports]
if {![file exists $project_file]} {error "Synthesis project is missing: $project_file"}
open_project $project_file
open_run synth_1
current_instance
set top_modules [get_cells -quiet -filter {IS_PRIMITIVE == 0}]
if {[llength $top_modules] > 0} {
  show_schematic -name "FFN synthesized module hierarchy" $top_modules
  if {[catch {write_schematic -force -format svg -scope all -name "FFN synthesized module hierarchy" [file join $report_dir vivado_top_modules.svg]} why]} {
    puts "SCHEMATIC_EXPORT_NOTE=$why"
    catch {write_schematic -force -name "FFN synthesized module hierarchy" [file join $report_dir vivado_top_modules.sch]}
  }
}
if {[llength [get_cells -quiet u_x]] > 0} {
  current_instance u_x
  show_schematic -name "X SRAM synthesized internal structure" [get_nets]
  if {[catch {write_schematic -force -format svg -scope all -name "X SRAM synthesized internal structure" [file join $report_dir vivado_x_sram.svg]} why]} {
    puts "SCHEMATIC_EXPORT_NOTE=$why"
    catch {write_schematic -force -name "X SRAM synthesized internal structure" [file join $report_dir vivado_x_sram.sch]}
  }
  current_instance
}
select_objects $top_modules
set fd [open [file join $report_dir gui_opened.txt] w]
puts $fd "Synthesis project opened in Vivado [version -short]"
puts $fd "Project: $project_file"
puts $fd "Top-level modules selected: [llength $top_modules]"
puts $fd "Expand Netlist > ffn_accel to inspect hierarchy."
close $fd
puts "VIVADO_HIERARCHY_GUI_READY"
