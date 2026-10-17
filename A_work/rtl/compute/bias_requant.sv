`timescale 1ns/1ps
// signed40 MAC + signed40 aligned bias -> signed41 sum -> signed16 result.
// Runtime right shift 0..63, nearest rounding with ties away from zero.
// Output register and valid remain stable throughout backpressure.
module bias_requant (
    input  logic clk,
    input  logic rst_n,
    input  logic in_valid,
    output logic in_ready,
    input  logic signed [39:0] in_acc,
    input  logic signed [39:0] in_bias,
    input  logic [5:0] in_shift,
    output logic out_valid,
    input  logic out_ready,
    output logic signed [15:0] out_data
);
    typedef enum logic [2:0] {IDLE, ABS_VALUE, SHIFT_VALUE, CONVERT, WAIT_OUTPUT} state_t;
    state_t state;
    logic signed [40:0] total_q;
    logic [40:0] magnitude_q;
    logic [41:0] shifted_q;
    logic negative_q;
    logic [5:0] shift_q;
    logic [40:0] quotient;
    logic [15:0] rounded_low;
    logic signed [15:0] converted;
    assign in_ready = (state == IDLE);
    always_comb begin
        // Appending a zero before shifting retains the HALF bit separately.
        // For shift=0 that bit is 0. For shift>=42 both fields become zero.
        quotient = shifted_q[41:1];
        rounded_low = quotient[15:0] + {15'd0,shifted_q[0]};
        if (negative_q) begin
            if (quotient >= 41'd32768) converted = 16'sh8000;
            else converted = -$signed(rounded_low);
        end else begin
            if (quotient > 41'd32767 || (quotient == 41'd32767 && shifted_q[0]))
                converted = 16'sh7fff;
            else converted = $signed(rounded_low);
        end
    end
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE;
            total_q <= 0;
            magnitude_q <= 0;
            shifted_q <= 0;
            negative_q <= 0;
            shift_q <= 0;
            out_valid <= 0;
            out_data <= 0;
        end else begin
            case (state)
                IDLE: if (in_valid && in_ready) begin
                    total_q <= {in_acc[39],in_acc} + {in_bias[39],in_bias};
                    shift_q <= in_shift;
                    state <= ABS_VALUE;
                end
                ABS_VALUE: begin
                    magnitude_q <= total_q[40] ? $unsigned(-total_q) : $unsigned(total_q);
                    negative_q <= total_q[40];
                    state <= SHIFT_VALUE;
                end
                SHIFT_VALUE: begin
                    shifted_q <= {magnitude_q,1'b0} >> shift_q;
                    state <= CONVERT;
                end
                CONVERT: begin
                    out_data <= converted;
                    out_valid <= 1;
                    state <= WAIT_OUTPUT;
                end
                WAIT_OUTPUT: if (out_valid && out_ready) begin
                    out_valid <= 0;
                    state <= IDLE;
                end
                default: begin
                    state <= IDLE;
                    out_valid <= 0;
                end
            endcase
        end
    end
endmodule
