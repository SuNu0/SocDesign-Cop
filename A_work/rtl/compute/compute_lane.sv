`timescale 1ns/1ps
// Integration example for B: metadata is sampled with FIRST accepted operand.
// Exactly 64 accepted operand pairs form one task. No explicit start/last.
// Latency is variable with input gaps / output backpressure.
module compute_lane (
    input  logic clk,
    input  logic rst_n,
    input  logic in_valid,
    output logic in_ready,
    input  logic signed [15:0] in_x,
    input  logic signed [15:0] in_w,
    input  logic signed [39:0] in_bias,
    input  logic [5:0] in_shift,
    output logic out_valid,
    input  logic out_ready,
    output logic signed [15:0] out_data
);
    logic [5:0] index;
    logic signed [39:0] bias_q;
    logic [5:0] shift_q;
    logic mac_valid, mac_ready;
    logic signed [39:0] mac_acc;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            index <= 0;
            bias_q <= 0;
            shift_q <= 0;
        end else if (in_valid && in_ready) begin
            if (index == 0) begin
                bias_q <= in_bias;
                shift_q <= in_shift;
            end
            index <= index + 1'b1;
        end
    end
    dot64_mac u_mac(.clk(clk),.rst_n(rst_n),.in_valid(in_valid),.in_ready(in_ready),
        .in_x(in_x),.in_w(in_w),.out_valid(mac_valid),.out_ready(mac_ready),.out_acc(mac_acc));
    bias_requant u_requant(.clk(clk),.rst_n(rst_n),.in_valid(mac_valid),.in_ready(mac_ready),
        .in_acc(mac_acc),.in_bias(bias_q),.in_shift(shift_q),
        .out_valid(out_valid),.out_ready(out_ready),.out_data(out_data));
endmodule
