`timescale 1ns/1ps
// A/B integration: the original B scheduler with A's signed16 compute lane.
// C supplies per-task shift metadata together with start/layer_id. Tensor memory
// requests retain B's logical element-index protocol (not a physical SoC bus).
module linear_accel_a_top #(
    parameter integer ROWS=99, COLS=256, BUS_W=64
) (
    input wire clk, rst_n, start,
    input wire [3:0] layer_id,
    input wire [5:0] task_shift,
    output reg [5:0] active_shift,
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
    input wire mem_rsp_error
);
    wire mac_clear, mac_in_valid, mac_in_ready, mac_first, mac_last;
    wire mac_out_valid, mac_out_ready, mac_error;
    wire [15:0] mac_x, mac_w, mac_result;
    wire [39:0] mac_bias;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) active_shift <= 0;
        else if (start && start_ready) active_shift <= task_shift;
    end

    linear_accel_top #(.ROWS(ROWS), .INNER(64), .COLS(COLS),
        .DATA_W(16), .BIAS_W(40), .RESULT_W(16), .BUS_W(BUS_W)) u_b (
        .clk(clk), .rst_n(rst_n), .start(start), .layer_id(layer_id),
        .start_ready(start_ready), .busy(busy), .done(done), .error(error),
        .start_rejected(start_rejected), .active_layer(active_layer), .error_code(error_code),
        .completed_outputs(completed_outputs), .task_cycles(task_cycles),
        .mem_req_valid(mem_req_valid), .mem_req_write(mem_req_write), .mem_req_ready(mem_req_ready),
        .mem_req_tensor(mem_req_tensor), .mem_req_index(mem_req_index), .mem_req_wdata(mem_req_wdata),
        .mem_rsp_valid(mem_rsp_valid), .mem_rsp_ready(mem_rsp_ready), .mem_rsp_rdata(mem_rsp_rdata),
        .mem_rsp_error(mem_rsp_error),
        .mac_clear(mac_clear), .mac_in_valid(mac_in_valid), .mac_in_ready(mac_in_ready),
        .mac_x(mac_x), .mac_w(mac_w), .mac_bias(mac_bias), .mac_first(mac_first), .mac_last(mac_last),
        .mac_out_valid(mac_out_valid), .mac_out_ready(mac_out_ready), .mac_result(mac_result), .mac_error(mac_error)
    );
    a_compute_adapter u_adapter (
        .clk(clk), .rst_n(rst_n), .mac_clear(mac_clear),
        .mac_in_valid(mac_in_valid), .mac_in_ready(mac_in_ready),
        .mac_x(mac_x), .mac_w(mac_w), .mac_bias(mac_bias), .mac_shift(active_shift),
        .mac_first(mac_first), .mac_last(mac_last),
        .mac_out_valid(mac_out_valid), .mac_out_ready(mac_out_ready),
        .mac_result(mac_result), .mac_error(mac_error)
    );
endmodule
