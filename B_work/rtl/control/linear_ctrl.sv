`timescale 1ns/1ps
// B v0 controller: one external transaction and one dot product in flight.
// No arithmetic, quantization, physical address mapping, or CSR ownership here.
module linear_ctrl #(
    parameter integer ROWS=99, INNER=64, COLS=256,
    parameter integer DATA_W=16, BIAS_W=40, RESULT_W=40, BUS_W=64
) (
    input wire clk, rst_n,
    input wire start,
    input wire [3:0] layer_id,
    output wire start_ready, busy, done, error,
    output reg start_rejected,
    output reg [3:0] active_layer,
    output reg [3:0] error_code,
    output reg [31:0] completed_outputs, task_cycles,

    output reg mem_req_valid, mem_req_write,
    input wire mem_req_ready,
    output reg [1:0] mem_req_tensor,
    output reg [31:0] mem_req_index,
    output reg [BUS_W-1:0] mem_req_wdata,
    input wire mem_rsp_valid,
    output reg mem_rsp_ready,
    input wire [BUS_W-1:0] mem_rsp_rdata,
    input wire mem_rsp_error,

    output reg x_wr_en, w_wr_en, b_wr_en,
    output reg [31:0] x_wr_addr, w_wr_addr, b_wr_addr,
    output wire [DATA_W-1:0] x_wr_data, w_wr_data,
    output wire [BIAS_W-1:0] b_wr_data,
    output reg x_rd_en, w_rd_en, b_rd_en,
    output reg [31:0] x_rd_addr, w_rd_addr, b_rd_addr,
    input wire x_rd_valid, w_rd_valid, b_rd_valid,
    input wire [DATA_W-1:0] x_rd_data, w_rd_data,
    input wire [BIAS_W-1:0] b_rd_data,
    input wire buffer_error,

    output wire mac_clear,
    output wire mac_in_valid,
    input wire mac_in_ready,
    output reg [DATA_W-1:0] mac_x, mac_w,
    output reg [BIAS_W-1:0] mac_bias,
    output wire mac_first, mac_last,
    input wire mac_out_valid,
    output wire mac_out_ready,
    input wire [RESULT_W-1:0] mac_result,
    input wire mac_error
);
    localparam [4:0] IDLE=0, W_REQ=1, W_RSP=2, B_REQ=3, B_RSP=4,
        X_REQ=5, X_RSP=6, B_READ=7, B_WAIT=8, PAIR_READ=9,
        PAIR_WAIT=10, PAIR_SEND=11, RESULT_WAIT=12, Y_REQ=13,
        Y_RSP=14, FINISH=15, FAULT=16;
    reg [4:0] state;
    reg [31:0] load_index, row_index, col_index, inner_index;
    reg have_x, have_w;
    reg [RESULT_W-1:0] result_hold;
    wire computing = state >= B_READ && state <= RESULT_WAIT;
    assign start_ready = state == IDLE;
    assign busy = state != IDLE && state != FINISH && state != FAULT;
    assign done = state == FINISH;
    assign error = state == FAULT;
    assign mac_clear = !rst_n || !computing;
    assign mac_in_valid = state == PAIR_SEND;
    assign mac_first = inner_index == 0;
    assign mac_last = inner_index == INNER-1;
    assign mac_out_ready = state == RESULT_WAIT;
    assign x_wr_data = mem_rsp_rdata[DATA_W-1:0];
    assign w_wr_data = mem_rsp_rdata[DATA_W-1:0];
    assign b_wr_data = mem_rsp_rdata[BIAS_W-1:0];

    always @* begin
        mem_req_valid=0; mem_req_write=0; mem_req_tensor=0;
        mem_req_index=0; mem_req_wdata=0; mem_rsp_ready=0;
        x_wr_en=0; w_wr_en=0; b_wr_en=0;
        x_wr_addr=load_index; w_wr_addr=load_index; b_wr_addr=load_index;
        x_rd_en=0; w_rd_en=0; b_rd_en=0;
        x_rd_addr=inner_index; w_rd_addr=inner_index*COLS+col_index;
        b_rd_addr=col_index;
        case (state)
            W_REQ: begin mem_req_valid=1; mem_req_tensor=1; mem_req_index=load_index; end
            W_RSP: begin
                mem_rsp_ready=1;
                w_wr_en=mem_rsp_valid && !mem_rsp_error;
            end
            B_REQ: begin mem_req_valid=1; mem_req_tensor=2; mem_req_index=load_index; end
            B_RSP: begin
                mem_rsp_ready=1;
                b_wr_en=mem_rsp_valid && !mem_rsp_error;
            end
            X_REQ: begin mem_req_valid=1; mem_req_tensor=0; mem_req_index=row_index*INNER+load_index; end
            X_RSP: begin
                mem_rsp_ready=1;
                x_wr_en=mem_rsp_valid && !mem_rsp_error;
            end
            B_READ: b_rd_en=1;
            PAIR_READ: begin x_rd_en=1; w_rd_en=1; end
            Y_REQ: begin
                mem_req_valid=1; mem_req_write=1; mem_req_tensor=3;
                mem_req_index=row_index*COLS+col_index;
                mem_req_wdata={{(BUS_W-RESULT_W){1'b0}}, result_hold};
            end
            Y_RSP: mem_rsp_ready=1;
            default: begin end
        endcase
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state<=IDLE; active_layer<=0; error_code<=0; start_rejected<=0;
            completed_outputs<=0; task_cycles<=0; load_index<=0;
            row_index<=0; col_index<=0; inner_index<=0;
            have_x<=0; have_w<=0; mac_x<=0; mac_w<=0; mac_bias<=0; result_hold<=0;
        end else begin
            start_rejected <= start && !start_ready;
            if (busy) task_cycles <= task_cycles+1;
            if (busy && (buffer_error || (computing && mac_error))) begin
                error_code <= buffer_error ? 4'd4 : 4'd3;
                state <= FAULT;
            end else begin
                case (state)
                    IDLE: if (start) begin
                        active_layer<=layer_id; completed_outputs<=0; task_cycles<=0;
                        error_code<=0; load_index<=0; row_index<=0; col_index<=0;
                        inner_index<=0; have_x<=0; have_w<=0;
                        if (layer_id >= 12) begin error_code<=2; state<=FAULT; end
                        else state<=W_REQ;
                    end
                    W_REQ: if (mem_req_ready) state<=W_RSP;
                    W_RSP: if (mem_rsp_valid) begin
                        if (mem_rsp_error) begin error_code<=1; state<=FAULT; end
                        else if (load_index == INNER*COLS-1) begin load_index<=0; state<=B_REQ; end
                        else begin load_index<=load_index+1; state<=W_REQ; end
                    end
                    B_REQ: if (mem_req_ready) state<=B_RSP;
                    B_RSP: if (mem_rsp_valid) begin
                        if (mem_rsp_error) begin error_code<=1; state<=FAULT; end
                        else if (load_index == COLS-1) begin load_index<=0; state<=X_REQ; end
                        else begin load_index<=load_index+1; state<=B_REQ; end
                    end
                    X_REQ: if (mem_req_ready) state<=X_RSP;
                    X_RSP: if (mem_rsp_valid) begin
                        if (mem_rsp_error) begin error_code<=1; state<=FAULT; end
                        else if (load_index == INNER-1) begin load_index<=0; state<=B_READ; end
                        else begin load_index<=load_index+1; state<=X_REQ; end
                    end
                    B_READ: state<=B_WAIT;
                    B_WAIT: if (b_rd_valid) begin mac_bias<=b_rd_data; inner_index<=0; state<=PAIR_READ; end
                    PAIR_READ: begin have_x<=0; have_w<=0; state<=PAIR_WAIT; end
                    PAIR_WAIT: begin
                        if (x_rd_valid) begin mac_x<=x_rd_data; have_x<=1; end
                        if (w_rd_valid) begin mac_w<=w_rd_data; have_w<=1; end
                        if ((have_x || x_rd_valid) && (have_w || w_rd_valid)) state<=PAIR_SEND;
                    end
                    PAIR_SEND: if (mac_in_ready) begin
                        if (inner_index == INNER-1) state<=RESULT_WAIT;
                        else begin inner_index<=inner_index+1; state<=PAIR_READ; end
                    end
                    RESULT_WAIT: if (mac_out_valid) begin result_hold<=mac_result; state<=Y_REQ; end
                    Y_REQ: if (mem_req_ready) state<=Y_RSP;
                    Y_RSP: if (mem_rsp_valid) begin
                        if (mem_rsp_error) begin error_code<=1; state<=FAULT; end
                        else begin
                            completed_outputs<=completed_outputs+1;
                            if (col_index != COLS-1) begin col_index<=col_index+1; state<=B_READ; end
                            else if (row_index != ROWS-1) begin
                                row_index<=row_index+1; col_index<=0; load_index<=0; state<=X_REQ;
                            end else state<=FINISH;
                        end
                    end
                    FINISH, FAULT: state<=IDLE;
                    default: begin error_code<=5; state<=FAULT; end
                endcase
            end
        end
    end
`ifndef SYNTHESIS
    initial begin
        if (ROWS<1 || INNER<1 || COLS<1 || DATA_W<1 || BIAS_W<1 || RESULT_W<1 || BUS_W<1 ||
            DATA_W>BUS_W || BIAS_W>BUS_W || RESULT_W>BUS_W)
            $fatal(1, "Invalid controller dimensions or widths");
    end
`endif
endmodule
