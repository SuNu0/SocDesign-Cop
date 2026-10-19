`timescale 1ns/1ps

// Independent buffer regression. No matrix/MAC model is involved.
module buffer_edge_case #(
    parameter integer CASE_ID=0,
    parameter integer WORD_W=40,
    parameter integer DEPTH=129,
    parameter integer MACRO_DEPTH=128,
    parameter integer AW=(DEPTH > 1) ? $clog2(DEPTH) : 1
)(output reg done);
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0,wr_en=0,rd_en=0;
    reg [AW-1:0] wr_addr=0,rd_addr=0;
    reg [WORD_W-1:0] wr_data=0;
    wire rd_valid,address_error,port_conflict;
    wire [WORD_W-1:0] rd_data;
    reg [WORD_W-1:0] expected[0:DEPTH-1];
    integer i;

    tensor_buffer #(.WORD_W(WORD_W),.DEPTH(DEPTH),.MACRO_DEPTH(MACRO_DEPTH)) dut(.*);

    function automatic [WORD_W-1:0] pattern(input integer index,input integer epoch);
        reg [31:0] seed;
        integer bit_index;
        begin
            seed=(index+1)*32'h9e3779b9 ^ (epoch+1)*32'h85ebca6b;
            for (bit_index=0;bit_index<WORD_W;bit_index=bit_index+1) begin
                seed=seed^(seed<<13);
                seed=seed^(seed>>17);
                seed=seed^(seed<<5);
                pattern[bit_index]=seed[0];
            end
        end
    endfunction

    task automatic check_flags(input bit ev,input bit ea,input bit ec);
        begin
            if (rd_valid!==ev || address_error!==ea || port_conflict!==ec)
                $fatal(1,"case %0d flags valid/address/conflict=%b%b%b expected=%b%b%b",
                       CASE_ID,rd_valid,address_error,port_conflict,ev,ea,ec);
        end
    endtask

    task automatic write_word(input integer index,input integer epoch);
        begin
            @(negedge clk);
            wr_en=1;rd_en=0;wr_addr=index;wr_data=pattern(index,epoch);
            @(posedge clk);#1;
            check_flags(0,0,0);
            expected[index]=wr_data;
        end
    endtask

    task automatic read_word(input integer index);
        begin
            @(negedge clk);
            wr_en=0;rd_en=1;rd_addr=index;
            @(posedge clk);#1;
            check_flags(1,0,0);
            if (rd_data!==expected[index])
                $fatal(1,"case %0d addr %0d read %h expected %h",CASE_ID,index,rd_data,expected[index]);
        end
    endtask

    initial begin
        done=0;
        repeat (2) @(negedge clk);
        rst_n=1;
        for(i=0;i<DEPTH;i=i+1) write_word(i,0);
        for(i=0;i<DEPTH;i=i+1) read_word(i);
        for(i=DEPTH-1;i>=0;i=i-1) read_word(i);

        // A legal conflict reports the conflict, grants the write, and emits no read-valid.
        @(negedge clk);
        wr_en=1;rd_en=1;wr_addr=DEPTH-1;rd_addr=0;wr_data=pattern(DEPTH-1,1);
        @(posedge clk);#1;
        check_flags(0,0,1);
        expected[DEPTH-1]=wr_data;
        read_word(DEPTH-1);
        read_word(0);

        // Non-power-of-two logical sizes have representable illegal addresses.
        if ((1<<AW)>DEPTH) begin
            @(negedge clk);
            wr_en=1;rd_en=0;wr_addr=DEPTH;wr_data=pattern(0,2);
            @(posedge clk);#1;
            check_flags(0,1,0);
            @(negedge clk);
            wr_en=0;rd_en=1;rd_addr=DEPTH;
            @(posedge clk);#1;
            check_flags(0,1,0);
            // Neither illegal operation may corrupt any valid location.
            for(i=0;i<DEPTH;i=i+1) read_word(i);
        end

        // No request after reset: validity is cleared, storage contents survive.
        @(negedge clk);
        wr_en=0;rd_en=0;rst_n=0;
        #1;
        if(rd_valid!==0) $fatal(1,"case %0d asynchronous reset did not clear rd_valid",CASE_ID);
        repeat(2) @(negedge clk);
        rst_n=1;
        read_word(0);
        read_word(DEPTH-1);

        @(negedge clk);
        wr_en=0;rd_en=0;
        @(posedge clk);#1;
        check_flags(0,0,0);
        $display("PASS buffer edges case=%0d width=%0d depth=%0d macro=%0d",CASE_ID,WORD_W,DEPTH,MACRO_DEPTH);
        done=1;
    end
endmodule

module tb_tensor_buffer_edges;
    wire [8:0] done;
    buffer_edge_case #(.CASE_ID(0),.WORD_W(1),.DEPTH(1),.MACRO_DEPTH(128)) c0(done[0]);
    buffer_edge_case #(.CASE_ID(1),.WORD_W(16),.DEPTH(127),.MACRO_DEPTH(128)) c1(done[1]);
    buffer_edge_case #(.CASE_ID(2),.WORD_W(17),.DEPTH(128),.MACRO_DEPTH(128)) c2(done[2]);
    buffer_edge_case #(.CASE_ID(3),.WORD_W(40),.DEPTH(129),.MACRO_DEPTH(128)) c3(done[3]);
    buffer_edge_case #(.CASE_ID(4),.WORD_W(65),.DEPTH(257),.MACRO_DEPTH(128)) c4(done[4]);
    buffer_edge_case #(.CASE_ID(5),.WORD_W(40),.DEPTH(1025),.MACRO_DEPTH(1024)) c5(done[5]);
    buffer_edge_case #(.CASE_ID(6),.WORD_W(16),.DEPTH(4097),.MACRO_DEPTH(4096)) c6(done[6]);
    buffer_edge_case #(.CASE_ID(7),.WORD_W(31),.DEPTH(256),.MACRO_DEPTH(128)) c7(done[7]);
    buffer_edge_case #(.CASE_ID(8),.WORD_W(33),.DEPTH(385),.MACRO_DEPTH(128)) c8(done[8]);
    initial begin
        wait(&done);
        $display("PASS all 9 buffer width/bank/address/conflict/reset cases");
        $finish;
    end
    initial begin
        #1000000;
        $fatal(1,"buffer regression timeout");
    end
endmodule
