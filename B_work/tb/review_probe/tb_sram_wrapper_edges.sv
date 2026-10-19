`timescale 1ns/1ps

module sram_edge_case #(parameter integer DEPTH=128, AW=$clog2(DEPTH))(output reg done);
    reg clk=0;
    always #5 clk=~clk;
    reg en=0,we=0;
    reg [AW-1:0] addr=0;
    reg [15:0] wdata=0;
    wire [15:0] rdata;
    sram_wrapper #(.DEPTH(DEPTH)) dut(.*);

    initial begin
        done=0;
        // Initialize two opposite address boundaries.
        @(negedge clk);en=1;we=1;addr=0;wdata=16'h1234;
        @(negedge clk);addr=DEPTH-1;wdata=16'habcd;
        @(negedge clk);we=0;addr=0;
        @(posedge clk);#1;
        if(rdata!==16'h1234) $fatal(1,"depth %0d first address read failed",DEPTH);
        // Disabled writes must neither alter SRAM nor update output.
        @(negedge clk);en=0;we=1;addr=0;wdata=16'hdead;
        @(posedge clk);#1;
        if(rdata!==16'h1234) $fatal(1,"depth %0d disabled access changed output",DEPTH);
        @(negedge clk);en=1;we=0;addr=0;
        @(posedge clk);#1;
        if(rdata!==16'h1234) $fatal(1,"depth %0d disabled write corrupted array",DEPTH);
        // Enabled writes change the array but preserve the preceding read output.
        @(negedge clk);we=1;addr=DEPTH-1;wdata=16'h55aa;
        @(posedge clk);#1;
        if(rdata!==16'h1234) $fatal(1,"depth %0d write updated read output",DEPTH);
        @(negedge clk);we=0;
        @(posedge clk);#1;
        if(rdata!==16'h55aa) $fatal(1,"depth %0d last address readback failed",DEPTH);
        @(negedge clk);en=0;addr=0;
        @(posedge clk);#1;
        if(rdata!==16'h55aa) $fatal(1,"depth %0d disabled read changed output",DEPTH);
        $display("PASS SRAM depth=%0d enable/write/read/hold/address boundaries",DEPTH);
        done=1;
    end
endmodule

module tb_sram_wrapper_edges;
    wire [2:0] done;
    sram_edge_case #(.DEPTH(128)) c0(done[0]);
    sram_edge_case #(.DEPTH(1024)) c1(done[1]);
    sram_edge_case #(.DEPTH(4096)) c2(done[2]);
    initial begin
        wait(&done);
        $display("PASS all 3 SRAM geometry cases");
        $finish;
    end
    initial begin
        #1000;
        $fatal(1,"SRAM regression timeout");
    end
endmodule
