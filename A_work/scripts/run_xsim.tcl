# Usage: vivado -mode batch -source run_xsim.tcl -tclargs <vectors> <build>
set root [file normalize [file join [file dirname [info script]] ..]]
set vectors [file normalize [lindex $argv 0]]
set build [file normalize [lindex $argv 1]]
set manifest_file [open [file join $vectors manifest.json] r]
set manifest [read $manifest_file]
close $manifest_file
if {![regexp {"dot_cases":\s*([0-9]+)} $manifest -> dots]} {error "Missing dot_cases"}
if {![regexp {"requant_cases":\s*([0-9]+)} $manifest -> rq]} {error "Missing requant_cases"}
create_project a_compute $build -part xc7z020clg400-1 -force
add_files [glob [file join $root rtl compute *.sv]]
set_property top compute_lane [current_fileset]
add_files -fileset sim_1 [file join $root tb tb_a_compute.sv]
set_property top tb_a_compute [get_filesets sim_1]
set_property target_simulator XSim [current_project]
set_property xsim.simulate.runtime {100 ms} [get_filesets sim_1]
set_property -dict [list xsim.simulate.xsim.more_options "-testplusarg VECTORS=$vectors -testplusarg DOT_CASES=$dots -testplusarg RQ_CASES=$rq"] [get_filesets sim_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1
puts "A_XSIM_PREFLIGHT part=[get_property PART [current_project]] top=[get_property TOP [get_filesets sim_1]] simulator=[get_property target_simulator [current_project]] dots=$dots requant=$rq"
launch_simulation -simset sim_1 -mode behavioral
close_sim
close_project
puts "A_XSIM_TCL_COMPLETED_CHECK_SIMULATE_LOG_FOR_PASS"
exit
