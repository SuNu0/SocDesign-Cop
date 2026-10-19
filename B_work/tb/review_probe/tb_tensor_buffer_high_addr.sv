`timescale 1ns/1ps

// Keep all upstream address bits until the buffer validates range.
module tb_tensor_buffer_high_addr;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0,wr_en=0,rd_en=0;
    reg [31:0] wr_addr=0,rd_addr=0;
    reg [39:0] wr_data=0;
    wire [39:0] rd_data;
    wire rd_valid,address_error,port_conflict;
    tensor_buffer #(.WORD_W(40),.DEPTH(129),.MACRO_DEPTH(128),.ADDR_W(32)) dut(.*);

    task automatic expect_read(input reg [31:0] index,input reg [39:0] data);
        begin
            @(negedge clk);wr_en=0;rd_en=1;rd_addr=index;
            @(posedge clk);#1;
            if(rd_valid!==1 || address_error!==0 || port_conflict!==0 || rd_data!==data)
                $fatal(1,"valid address %h failed: data=%h expected=%h",index,rd_data,data);
        end
    endtask

    task automatic reject_write(input reg [31:0] index);
        begin
            @(negedge clk);wr_en=1;rd_en=0;wr_addr=index;wr_data=40'hbadbadbadb;
            @(posedge clk);#1;
            if(address_error!==1 || rd_valid!==0 || port_conflict!==0)
                $fatal(1,"illegal high-bit write address %h was not rejected",index);
        end
    endtask

    task automatic reject_read(input reg [31:0] index);
        begin
            @(negedge clk);wr_en=0;rd_en=1;rd_addr=index;
            @(posedge clk);#1;
            if(address_error!==1 || rd_valid!==0 || port_conflict!==0)
                $fatal(1,"illegal high-bit read address %h was not rejected",index);
        end
    endtask

    initial begin
        repeat(2) @(negedge clk);
        rst_n=1;
        @(negedge clk);wr_en=1;wr_addr=0;wr_data=40'h0123456789;
        @(negedge clk);wr_addr=128;wr_data=40'hfedcba9876;
        expect_read(0,40'h0123456789);
        expect_read(128,40'hfedcba9876);
        reject_write(32'h00000100); // Would alias location 0 if truncated to 8 bits.
        reject_write(32'h00000180); // Would alias location 128 if truncated.
        reject_write(32'h80000000);
        reject_write(32'hffffffff);
        reject_read(32'h00000100);
        reject_read(32'h00000180);
        reject_read(32'h80000000);
        reject_read(32'hffffffff);
        expect_read(0,40'h0123456789);
        expect_read(128,40'hfedcba9876);
        $display("PASS 32-bit high-address rejection without valid-address corruption");
        $finish;
    end
    initial begin
        #2000;
        $fatal(1,"high address regression timeout");
    end
endmodule
