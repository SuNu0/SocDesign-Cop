`timescale 1ns/1ps

// Reset must block access without clearing initialized SRAM contents.
module tb_tensor_buffer_reset_probe;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0,wr_en=0,rd_en=0;
    reg [7:0] wr_addr=0,rd_addr=0;
    reg [39:0] wr_data=0;
    wire [39:0] rd_data;
    wire rd_valid,address_error,port_conflict;
    tensor_buffer #(.WORD_W(40),.DEPTH(129),.MACRO_DEPTH(128)) dut(.*);

    initial begin
        repeat(2) @(negedge clk);
        rst_n=1;
        @(negedge clk);
        wr_en=1;wr_addr=128;wr_data=40'h0123456789;
        @(negedge clk);
        rst_n=0;wr_data=40'hfedcba9876;
        repeat(2) @(negedge clk);
        wr_en=0;
        rst_n=1;
        rd_en=1;rd_addr=128;
        @(posedge clk);#1;
        if(rd_valid!==1) $fatal(1,"read did not complete after reset");
        if(rd_data!==40'h0123456789)
            $fatal(1,"RESET WRITE LEAK: rst_n=0 overwrote live storage: got=%h expected=0123456789",rd_data);
        $display("PASS writes are blocked during reset; initialized SRAM data survives reset");
        $finish;
    end
    initial begin
        #1000;
        $fatal(1,"reset probe timeout");
    end
endmodule
