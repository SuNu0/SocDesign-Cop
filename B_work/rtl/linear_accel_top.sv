`timescale 1ns/1ps
// B-owned boundary: external A streaming MAC and external C tensor requests.
module linear_accel_top #(
    parameter integer ROWS=99, INNER=64, COLS=256,
    parameter integer DATA_W=16, BIAS_W=40, RESULT_W=40, BUS_W=64
) (
    input wire clk, rst_n, start,
    input wire [3:0] layer_id,
    output wire start_ready, busy, done, error, start_rejected,
    output wire [3:0] active_layer, error_code,
    output wire [31:0] completed_outputs, task_cycles,
    output wire mem_req_valid, mem_req_write,
    input wire mem_req_ready,
    output wire [1:0] mem_req_tensor,
    output wire [31:0] mem_req_index,
    output wire [BUS_W-1:0] mem_req_wdata,
    input wire mem_rsp_valid,
    output wire mem_rsp_ready,
    input wire [BUS_W-1:0] mem_rsp_rdata,
    input wire mem_rsp_error,
    output wire mac_clear, mac_in_valid,
    input wire mac_in_ready,
    output wire [DATA_W-1:0] mac_x, mac_w,
    output wire [BIAS_W-1:0] mac_bias,
    output wire mac_first, mac_last,
    input wire mac_out_valid,
    output wire mac_out_ready,
    input wire [RESULT_W-1:0] mac_result,
    input wire mac_error
);
    wire x_wr_en,w_wr_en,b_wr_en,x_rd_en,w_rd_en,b_rd_en;
    wire [31:0] x_wr_addr,w_wr_addr,b_wr_addr,x_rd_addr,w_rd_addr,b_rd_addr;
    wire [DATA_W-1:0] x_wr_data,w_wr_data,x_rd_data,w_rd_data;
    wire [BIAS_W-1:0] b_wr_data,b_rd_data;
    wire x_rd_valid,w_rd_valid,b_rd_valid;
    wire [2:0] addr_error,port_conflict;
    wire buffer_error=|addr_error || |port_conflict;
    linear_ctrl #(.ROWS(ROWS),.INNER(INNER),.COLS(COLS),.DATA_W(DATA_W),
        .BIAS_W(BIAS_W),.RESULT_W(RESULT_W),.BUS_W(BUS_W)) u_ctrl(.*);
    tensor_buffer #(.WORD_W(DATA_W),.DEPTH(INNER),.MACRO_DEPTH(128),.ADDR_W(32)) u_x (
        .clk(clk),.rst_n(rst_n),.wr_en(x_wr_en),.wr_addr(x_wr_addr),.wr_data(x_wr_data),
        .rd_en(x_rd_en),.rd_addr(x_rd_addr),.rd_valid(x_rd_valid),.rd_data(x_rd_data),
        .address_error(addr_error[0]),.port_conflict(port_conflict[0]));
    tensor_buffer #(.WORD_W(DATA_W),.DEPTH(INNER*COLS),.MACRO_DEPTH(4096),.ADDR_W(32)) u_w (
        .clk(clk),.rst_n(rst_n),.wr_en(w_wr_en),.wr_addr(w_wr_addr),.wr_data(w_wr_data),
        .rd_en(w_rd_en),.rd_addr(w_rd_addr),.rd_valid(w_rd_valid),.rd_data(w_rd_data),
        .address_error(addr_error[1]),.port_conflict(port_conflict[1]));
    tensor_buffer #(.WORD_W(BIAS_W),.DEPTH(COLS),.MACRO_DEPTH(128),.ADDR_W(32)) u_b (
        .clk(clk),.rst_n(rst_n),.wr_en(b_wr_en),.wr_addr(b_wr_addr),.wr_data(b_wr_data),
        .rd_en(b_rd_en),.rd_addr(b_rd_addr),.rd_valid(b_rd_valid),.rd_data(b_rd_data),
        .address_error(addr_error[2]),.port_conflict(port_conflict[2]));
endmodule
