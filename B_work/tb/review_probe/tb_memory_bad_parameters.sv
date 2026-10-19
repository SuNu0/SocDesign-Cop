`timescale 1ns/1ps

// These tops must exit nonzero at time zero with the corresponding RTL guard.
// Their watchdog deliberately exits successfully, so a missing guard cannot
// masquerade as an expected failure when the regression checks process status.
module tb_buffer_bad_addr_width;
    wire rd_valid,address_error,port_conflict;
    wire [15:0] rd_data;
    tensor_buffer #(.WORD_W(16),.DEPTH(129),.MACRO_DEPTH(128),.ADDR_W(7)) dut(
        .clk(1'b0),.rst_n(1'b0),.wr_en(1'b0),.wr_addr(7'd0),.wr_data(16'd0),
        .rd_en(1'b0),.rd_addr(7'd0),.rd_valid(rd_valid),.rd_data(rd_data),
        .address_error(address_error),.port_conflict(port_conflict));
    initial begin
        #20;
        $display("INVALID_PARAMETER_ACCEPTED: buffer ADDR_W=7 cannot address DEPTH=129");
        $finish;
    end
endmodule

module tb_sram_bad_addr_width;
    wire [15:0] rdata;
    sram_wrapper #(.DEPTH(128),.AW(6)) dut(
        .clk(1'b0),.en(1'b0),.we(1'b0),.addr(6'd0),.wdata(16'd0),.rdata(rdata));
    initial begin
        #20;
        $display("INVALID_PARAMETER_ACCEPTED: SRAM AW=6 does not match DEPTH=128");
        $finish;
    end
endmodule
