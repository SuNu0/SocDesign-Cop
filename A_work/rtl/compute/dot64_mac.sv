`timescale 1ns/1ps
// A contribution: one signed16 multiplier, 64 accepted beats per dot product.
// Contract: count advances ONLY on in_valid && in_ready. Reset aborts a task.
module dot64_mac (
    input  logic clk,
    input  logic rst_n,
    input  logic in_valid,
    output logic in_ready,
    input  logic signed [15:0] in_x,
    input  logic signed [15:0] in_w,
    output logic out_valid,
    input  logic out_ready,
    output logic signed [39:0] out_acc
);
    logic [5:0] count;
    logic signed [39:0] acc;
    logic signed [31:0] product;
    logic signed [39:0] next_acc;
    assign product = in_x * in_w;
    assign next_acc = acc + {{8{product[31]}}, product};
    assign in_ready = !out_valid;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            count <= 0;
            acc <= 0;
            out_acc <= 0;
            out_valid <= 0;
        end else begin
            if (out_valid && out_ready) out_valid <= 0;
            if (in_valid && in_ready) begin
                if (count == 63) begin
                    out_acc <= next_acc; // includes the LAST product, not old acc
                    out_valid <= 1;
                    count <= 0;
                    acc <= 0;
                end else begin
                    count <= count + 1'b1;
                    acc <= next_acc;
                end
            end
        end
    end
endmodule
