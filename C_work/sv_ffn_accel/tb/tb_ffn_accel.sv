`timescale 1ns/1ps
module tb_ffn_accel;
  import ffn_numeric_pkg::*;
  logic clk=0;
  always #3.333 clk=~clk;
  logic rst_n=0;
  logic cmd_valid=0,cmd_read=0,rsp_ready=0;
  logic [31:0] cmd_addr=0,cmd_wdata=0;
  logic [3:0] cmd_wmask=4'hf;
  wire cmd_ready,rsp_valid,rsp_err,irq;
  wire [31:0] rsp_rdata;
  ffn_accel dut (
    .clk(clk),.rst_n(rst_n),.i_icb_cmd_valid(cmd_valid),
    .o_icb_cmd_ready(cmd_ready),.i_icb_cmd_read(cmd_read),
    .i_icb_cmd_addr(cmd_addr),.i_icb_cmd_wdata(cmd_wdata),
    .i_icb_cmd_wmask(cmd_wmask),.o_icb_rsp_valid(rsp_valid),
    .i_icb_rsp_ready(rsp_ready),.o_icb_rsp_rdata(rsp_rdata),
    .o_icb_rsp_err(rsp_err),.o_irq(irq)
  );

  localparam [31:0] X_BASE=32'h10000,W_BASE=32'h20000,
                    B_BASE=32'h30000,Y_BASE=32'h40000;
  localparam integer EXPECTED_CYCLES=158400;
  logic [15:0] x_data[0:6335],w_data[0:16383],b_data[0:255],expected[0:25343];
  logic [31:0] expected_sat[0:0];
  integer layer,idx,layers=12,polls,errors=0,total_outputs=0;
  integer cycles_file,csv_file,cycle_result;
  longint unsigned tick=0,task_start,task_elapsed;
  string vectors_dir="build/vectors",result_dir="build",filename;
  logic [31:0] rd;
  logic observed_error;
  logic [16:0] quant_test;
  always @(posedge clk) tick<=tick+1;

  // Commands change only on falling edges. Responses are accepted explicitly.
  // Extra response stalls exercise VALID/data/error stability and READY exclusion.
  task automatic transaction(
    input bit read_not_write,input logic [31:0] address,input logic [31:0] data,
    input logic [3:0] mask,input integer stalls,
    output logic [31:0] result,output logic error_result
  );
    integer timeout,hold;
    logic [31:0] held_data;
    logic held_error;
    begin
      @(negedge clk);
      cmd_valid=1;cmd_read=read_not_write;cmd_addr=address;
      cmd_wdata=data;cmd_wmask=mask;rsp_ready=0;timeout=0;
      while (!cmd_ready) begin
        @(negedge clk); timeout=timeout+1;
        if(timeout>30)$fatal(1,"Command timed out addr=%h",address);
      end
      @(posedge clk); @(negedge clk);cmd_valid=0;timeout=0;
      while (!rsp_valid) begin
        @(negedge clk);timeout=timeout+1;
        if(timeout>30)$fatal(1,"Response timed out addr=%h",address);
      end
      held_data=rsp_rdata;held_error=rsp_err;
      for(hold=0;hold<stalls;hold=hold+1)begin
        @(posedge clk);@(negedge clk);
        if(rsp_valid!==1 || rsp_rdata!==held_data || rsp_err!==held_error || cmd_ready!==0)
          $fatal(1,"Response changed under backpressure addr=%h",address);
      end
      result=rsp_rdata;error_result=rsp_err;rsp_ready=1;
      @(posedge clk);@(negedge clk);rsp_ready=0;
    end
  endtask
  task automatic write_word(input logic [31:0] addr,input logic [31:0] value);
    logic [31:0] ignored;logic err;
    begin
      transaction(0,addr,value,4'hf,0,ignored,err);
      if(err!==0)$fatal(1,"Unexpected write error addr=%h data=%h",addr,value);
    end
  endtask
  task automatic read_word(input logic [31:0] addr,output logic [31:0] value);
    logic err;
    begin
      transaction(1,addr,0,4'hf,0,value,err);
      if(err!==0)$fatal(1,"Unexpected read error addr=%h",addr);
    end
  endtask
  task automatic expect_error(input bit read_op,input logic[31:0] addr,
                             input logic[31:0] value,input logic[3:0] mask);
    logic [31:0] ignored;logic err;
    begin
      transaction(read_op,addr,value,mask,2,ignored,err);
      if(err!==1)$fatal(1,"Expected bus error addr=%h",addr);
    end
  endtask
  task automatic apply_reset;
    begin
      @(negedge clk);rst_n=0;cmd_valid=0;rsp_ready=0;
      repeat(4)@(negedge clk);
      if(rsp_valid!==0 || irq!==0 || cmd_ready!==0)$fatal(1,"Reset did not quiesce interface");
      rst_n=1;repeat(2)@(negedge clk);
      read_word(32'h4,rd);
      if(rd!==0)$fatal(1,"Reset status should be idle/clear");
    end
  endtask
  task automatic load_fixture(input integer fixture_layer);
    begin
      filename=$sformatf("%s/layer_%02d_x.hex",vectors_dir,fixture_layer);$readmemh(filename,x_data);
      filename=$sformatf("%s/layer_%02d_w.hex",vectors_dir,fixture_layer);$readmemh(filename,w_data);
      filename=$sformatf("%s/layer_%02d_b.hex",vectors_dir,fixture_layer);$readmemh(filename,b_data);
      filename=$sformatf("%s/layer_%02d_y.hex",vectors_dir,fixture_layer);$readmemh(filename,expected);
      filename=$sformatf("%s/layer_%02d_sat.hex",vectors_dir,fixture_layer);$readmemh(filename,expected_sat);
      write_word(32'h20,fixture_layer);
      for(integer i=0;i<6336;i=i+1)write_word(X_BASE+4*i,{16'd0,x_data[i]});
      for(integer i=0;i<16384;i=i+1)write_word(W_BASE+4*i,{16'd0,w_data[i]});
      for(integer i=0;i<256;i=i+1)write_word(B_BASE+4*i,{16'd0,b_data[i]});
    end
  endtask
  task automatic check_quant(input logic signed[39:0] value,
                            input logic[15:0] want,input bit saturated);
    begin
      quant_test=requantize(value);
      if(quant_test!=={saturated,want})$fatal(1,"Quantizer mismatch acc=%d got=%h",value,quant_test);
    end
  endtask

  initial begin
    if($value$plusargs("VECTORS=%s",vectors_dir))begin end
    if($value$plusargs("RESULTS=%s",result_dir))begin end
    if($value$plusargs("LAYERS=%d",layers))begin end
    if(layers<1 || layers>12)$fatal(1,"LAYERS must be 1..12");
    if($test$plusargs("WAVES"))begin
      filename=$sformatf("%s/ffn_control.vcd",result_dir);$dumpfile(filename);
      // Keep waveforms compact: control/pipeline plus one representative MAC lane.
      $dumpvars(0,clk,rst_n,irq,cmd_valid,cmd_ready,rsp_valid,rsp_ready,rsp_err);
      $dumpvars(0,dut.state,dut.row_index,dut.group_index,dut.mac_issue,
                  dut.mac_read_valid,dut.product_valid,dut.product_last,dut.write_lane);
    end
    cycles_file=$fopen($sformatf("%s/performance.csv",result_dir),"w");
    if(!cycles_file)$fatal(1,"Cannot open performance output");
    $fdisplay(cycles_file,"layer,compute_cycles,host_end_to_end_cycles,saturation_count,outputs");
    check_quant(40'sd127,16'd0,0);check_quant(40'sd128,16'd1,0);
    check_quant(-40'sd127,16'd0,0);check_quant(-40'sd128,16'hffff,0);
    check_quant(40'sd384,16'd2,0);check_quant(-40'sd384,16'hfffe,0);
    check_quant(40'sd8388480,16'h7fff,1);
    check_quant(-40'sd8388736,16'h8000,1);
    check_quant(40'sd68719476736,16'h7fff,1);
    check_quant(-40'sd68719476736,16'h8000,1);
    apply_reset();
    read_word(32'h10,rd);if(rd!==99)$fatal(1,"Wrong row count");
    read_word(32'h14,rd);if(rd!==64)$fatal(1,"Wrong inner count");
    read_word(32'h18,rd);if(rd!==256)$fatal(1,"Wrong column count");
    read_word(32'h0c,rd);if(rd!==1622016)$fatal(1,"Wrong MAC count");
    read_word(32'h1c,rd);if(rd!==32'h810)$fatal(1,"Wrong number format");
    expect_error(1,32'hffff_0000,0,4'hf);
    expect_error(1,X_BASE+1,0,4'hf);
    expect_error(0,X_BASE,32'd1,4'h3);
    expect_error(0,Y_BASE,32'd1,4'hf);
    expect_error(1,32'h16300,0,4'hf);
    expect_error(1,32'h58c00,0,4'hf);
    expect_error(0,32'h4,0,4'hf);
    expect_error(0,32'h20,12,4'hf);
    expect_error(0,32'h0,4,4'hf);
    // Read stability under long response backpressure, including a memory read.
    write_word(X_BASE,32'h8000);
    transaction(1,X_BASE,0,4'hf,7,rd,observed_error);
    if(observed_error!==0 || rd!==32'hffff8000)$fatal(1,"Memory read/sign-extension/backpressure");
    transaction(1,32'h10,0,4'hf,5,rd,observed_error);
    if(observed_error!==0 || rd!==99)$fatal(1,"Register response backpressure");
    // Reset an in-flight SRAM read response and verify that no stale response survives.
    @(negedge clk);cmd_valid=1;cmd_read=1;cmd_addr=X_BASE;rsp_ready=0;
    @(posedge clk);@(negedge clk);cmd_valid=0;apply_reset();
    // Reset aborts compute without resetting SRAM arrays. Reload before use.
    load_fixture(0);write_word(0,1);repeat(90)@(negedge clk);
    if(dut.busy!==1)$fatal(1,"Expected active compute before reset");
    apply_reset();
    $display("PASS directed checks: quantizer, address errors, backpressure, reset response/compute");

    for(layer=0;layer<layers;layer=layer+1)begin
      task_start=tick;
      load_fixture(layer);
      // Confirm the last input/weight/bias and lane-bank mapping by bus readback.
      read_word(X_BASE+4*6335,rd);
      if(rd!=={{16{x_data[6335][15]}},x_data[6335]})$fatal(1,"Input readback mismatch");
      read_word(W_BASE+4*16383,rd);
      if(rd!=={{16{w_data[16383][15]}},w_data[16383]})$fatal(1,"Weight readback mismatch");
      read_word(B_BASE+4*255,rd);
      if(rd!=={{16{b_data[255][15]}},b_data[255]})$fatal(1,"Bias readback mismatch");
      read_word(32'h20,rd);if(rd!==layer)$fatal(1,"Layer tag mismatch");
      write_word(0,1);
      expect_error(0,0,1,4'hf); // START during busy must not restart the task.
      expect_error(0,X_BASE,0,4'hf);
      expect_error(1,Y_BASE,0,4'hf);
      expect_error(0,32'h20,0,4'hf);
      polls=0;rd=0;
      while(rd[1]!==1'b1)begin
        repeat(64)@(negedge clk);read_word(4,rd);polls=polls+1;
        if(polls>3000)$fatal(1,"Compute timeout layer=%0d",layer);
      end
      if(rd[0]!==0 || irq!==1)$fatal(1,"DONE/IRQ status mismatch");
      read_word(8,rd);cycle_result=rd;
      if(cycle_result!==EXPECTED_CYCLES)$fatal(1,"Cycle count got=%0d expected=%0d",cycle_result,EXPECTED_CYCLES);
      read_word(32'h24,rd);
      if(rd!==expected_sat[0])$fatal(1,"Saturation count got=%0d expected=%0d",rd,expected_sat[0]);
      csv_file=$fopen($sformatf("%s/rtl_layer_%02d.hex",result_dir,layer),"w");
      if(!csv_file)$fatal(1,"Cannot open RTL result file");
      for(idx=0;idx<25344;idx=idx+1)begin
        read_word(Y_BASE+4*idx,rd);
        $fdisplay(csv_file,"%04h",rd[15:0]);
        if(rd!=={{16{expected[idx][15]}},expected[idx]})begin
          if(errors<8)$display("MISMATCH layer=%0d row=%0d col=%0d got=%h expected=%h",layer,idx/256,idx%256,rd,expected[idx]);
          errors=errors+1;
        end
      end
      $fclose(csv_file);total_outputs=total_outputs+25344;task_elapsed=tick-task_start;
      $fdisplay(cycles_file,"%0d,%0d,%0d,%0d,%0d",layer,cycle_result,task_elapsed,expected_sat[0],25344);
      $display("PASS layer=%0d outputs=25344 compute_cycles=%0d host_cycles=%0d saturations=%0d",layer,cycle_result,task_elapsed,expected_sat[0]);
      // A new START must clear stale DONE; this is also checked by the next task.
      write_word(0,2);read_word(4,rd);
      if(rd!==0 || irq!==0)$fatal(1,"DONE acknowledge failed");
      if(errors!=0)$fatal(1,"Output mismatches=%0d",errors);
    end
    $fclose(cycles_file);
    $display("ALL TESTS PASSED layers=%0d outputs=%0d mismatches=%0d",layers,total_outputs,errors);
    $finish;
  end
  initial begin
    #100000000;$fatal(1,"Global simulation watchdog timeout");
  end
endmodule
