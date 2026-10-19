`timescale 1ns/1ps
// Bridge B's explicit dot boundary / clear contract to A's fixed dot64 lane.
// Only one complete dot and its result may be outstanding. Metadata is captured
// on the first accepted operand. Errors remain asserted until clear or reset.
module a_compute_adapter (
    input wire clk, rst_n,
    input wire mac_clear,
    input wire mac_in_valid,
    output wire mac_in_ready,
    input wire [15:0] mac_x, mac_w,
    input wire [39:0] mac_bias,
    input wire [5:0] mac_shift,
    input wire mac_first, mac_last,
    output wire mac_out_valid,
    input wire mac_out_ready,
    output wire [15:0] mac_result,
    output wire mac_error
);
    // mac_clear is a state decoder in B. Sample it into a register before it
    // can assert the lane's asynchronous reset; never use it as a reset net.
    // The global reset still asserts asynchronously. Deassertion is pipelined
    // through two clocked stages, and all external handshakes are masked until
    // the lane has been released. A's in_ready alone is high during its reset.
    reg local_reset_hold;
    (* ASYNC_REG = "TRUE" *) reg [1:0] release_pipe;
    wire lane_rst_n = rst_n && !local_reset_hold && release_pipe[1];
    wire enabled = rst_n && !mac_clear && lane_rst_n;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            local_reset_hold <= 1'b1;
            release_pipe <= 2'b00;
        end else begin
            local_reset_hold <= mac_clear;
            if (mac_clear || local_reset_hold) release_pipe <= 2'b00;
            else release_pipe <= {release_pipe[0], 1'b1};
        end
    end

    reg [5:0] beat_count;
    reg pending_result, fault;
    reg [39:0] bias_hold;
    reg [5:0] shift_hold;
    wire lane_in_ready, lane_out_valid;
    wire [15:0] lane_result;
    wire boundary_ok = (mac_first == (beat_count == 0)) &&
                       (mac_last == (beat_count == 63));
    wire lane_in_valid = enabled && !fault && !pending_result &&
                         mac_in_valid && boundary_ok;
    wire lane_out_ready = enabled && !fault && pending_result && mac_out_ready;
    wire [39:0] lane_bias = (beat_count == 0 && !pending_result) ? mac_bias : bias_hold;
    wire [5:0] lane_shift = (beat_count == 0 && !pending_result) ? mac_shift : shift_hold;
    assign mac_in_ready = enabled && !fault && !pending_result && lane_in_ready;
    assign mac_out_valid = enabled && !fault && pending_result && lane_out_valid;
    assign mac_result = lane_result;
    assign mac_error = fault;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            beat_count <= 0;
            pending_result <= 0;
            fault <= 0;
            bias_hold <= 0;
            shift_hold <= 0;
        end else if (mac_clear) begin
            beat_count <= 0;
            pending_result <= 0;
            fault <= 0;
            bias_hold <= 0;
            shift_hold <= 0;
        end else if (!lane_rst_n) begin
            beat_count <= 0;
            pending_result <= 0;
            bias_hold <= 0;
            shift_hold <= 0;
        end else if (!fault) begin
            if (lane_out_valid && !pending_result) fault <= 1;
            if (mac_in_valid && mac_in_ready) begin
                if (!boundary_ok) fault <= 1;
                else begin
                    if (beat_count == 0) begin
                        bias_hold <= mac_bias;
                        shift_hold <= mac_shift;
                    end
                    if (beat_count == 63) begin
                        beat_count <= 0;
                        pending_result <= 1;
                    end else beat_count <= beat_count + 1'b1;
                end
            end
            if (mac_out_valid && mac_out_ready) pending_result <= 0;
        end
    end

    compute_lane u_lane (
        .clk(clk), .rst_n(lane_rst_n),
        .in_valid(lane_in_valid), .in_ready(lane_in_ready),
        .in_x(mac_x), .in_w(mac_w), .in_bias(lane_bias), .in_shift(lane_shift),
        .out_valid(lane_out_valid), .out_ready(lane_out_ready), .out_data(lane_result)
    );
endmodule
