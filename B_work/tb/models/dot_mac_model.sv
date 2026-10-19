`timescale 1ns/1ps
// TEST ONLY. Replace with A's RTL after the team agrees the numerical contract.
// Test contract: signed 16-bit products, 40-bit modular sum including bias.
module dot_mac_model #(parameter integer INNER=64, STALLS=1) (
    input wire clk,rst_n,clear,inject_error,
    input wire in_valid,
    output wire in_ready,
    input wire [15:0] x,w,
    input wire [39:0] bias,
    input wire first,last,
    output reg out_valid,
    input wire out_ready,
    output reg [39:0] result,
    output reg error
);
    reg [31:0] random_state;
    reg signed [39:0] accumulator;
    reg [39:0] pending_result;
    integer terms, delay_count;
    reg pending;
    wire signed [31:0] product=$signed(x)*$signed(w);
    wire signed [39:0] extended_product={{8{product[31]}},product};
    wire signed [39:0] next_sum=(first ? $signed(bias) : accumulator)+extended_product;
    assign in_ready=rst_n && !clear && !pending && !out_valid && (!STALLS || random_state[0] || random_state[2]);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            random_state<=32'h41e9ac17; accumulator<=0; pending_result<=0;
            terms<=0; delay_count<=0; pending<=0; out_valid<=0; result<=0; error<=0;
        end else begin
            random_state<={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
            error<=0;
            if (clear) begin
                accumulator<=0; terms<=0; pending<=0; out_valid<=0; delay_count<=0;
            end else begin
                if (out_valid && out_ready) out_valid<=0;
                if (pending) begin
                    if (delay_count==0) begin out_valid<=1; result<=pending_result; pending<=0; end
                    else delay_count<=delay_count-1;
                end
                if (in_valid && in_ready) begin
                    if (first !== (terms==0) || last !== (terms==INNER-1))
                        $fatal(1,"Dot-product boundary violation terms=%0d first=%b last=%b",terms,first,last);
                    if (inject_error) error<=1;
                    accumulator<=next_sum;
                    if (last) begin
                        pending_result<=next_sum; pending<=1; terms<=0;
                        delay_count<=STALLS ? {29'd0,random_state[5:3]} : 0;
                    end else terms<=terms+1;
                end
            end
        end
    end
endmodule
