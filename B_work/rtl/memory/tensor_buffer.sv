`timescale 1ns/1ps
// Banked, lane-packed words built exclusively from 16-bit macro shapes.
// One access per clock; write has priority if both enables are asserted.
module tensor_buffer #(
    parameter integer WORD_W = 16,
    parameter integer DEPTH = 64,
    parameter integer MACRO_DEPTH = 128,
    parameter integer ADDR_W = (DEPTH > 1) ? $clog2(DEPTH) : 1
) (
    input wire clk, rst_n,
    input wire wr_en,
    input wire [ADDR_W-1:0] wr_addr,
    input wire [WORD_W-1:0] wr_data,
    input wire rd_en,
    input wire [ADDR_W-1:0] rd_addr,
    output reg rd_valid,
    output wire [WORD_W-1:0] rd_data,
    output wire address_error,
    output wire port_conflict
);
    localparam integer LANES = (WORD_W+15)/16;
    localparam integer PAD_W = LANES*16;
    localparam integer BANKS = (DEPTH+MACRO_DEPTH-1)/MACRO_DEPTH;
    localparam integer MAW = $clog2(MACRO_DEPTH);
    localparam integer BAW = (BANKS > 1) ? $clog2(BANKS) : 1;
    wire [ADDR_W-1:0] access_addr = wr_en ? wr_addr : rd_addr;
    wire [31:0] bank_index = access_addr / MACRO_DEPTH;
    wire [MAW-1:0] macro_addr = access_addr % MACRO_DEPTH;
    wire [PAD_W-1:0] padded_write = {{(PAD_W-WORD_W){1'b0}}, wr_data};
    wire [PAD_W-1:0] bank_data [0:BANKS-1];
    reg [BAW-1:0] read_bank;
    assign port_conflict = wr_en && rd_en;
    assign address_error = (wr_en && wr_addr >= DEPTH) || (rd_en && rd_addr >= DEPTH);
    assign rd_data = bank_data[read_bank][WORD_W-1:0];
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rd_valid <= 1'b0;
            read_bank <= 0;
        end else begin
            rd_valid <= rd_en && !wr_en && !address_error;
            if (rd_en && !wr_en && !address_error) read_bank <= bank_index[BAW-1:0];
        end
    end
    generate
        for (genvar b=0; b<BANKS; b=b+1) begin: g_bank
            localparam integer BANK_ID=b;
            wire selected=rst_n && (wr_en || rd_en) && !address_error && bank_index == BANK_ID;
            wire [PAD_W-1:0] this_bank_data;
            assign bank_data[BANK_ID]=this_bank_data;
            for (genvar l=0; l<LANES; l=l+1) begin: g_lane
                sram_wrapper #(.DEPTH(MACRO_DEPTH)) u_sram (
                    .clk(clk), .en(selected),
                    .we(wr_en), .addr(macro_addr),
                    .wdata(padded_write[l*16 +: 16]), .rdata(this_bank_data[l*16 +: 16])
                );
            end
        end
    endgenerate
`ifndef SYNTHESIS
    initial begin
        if (WORD_W < 1 || DEPTH < 1) $fatal(1, "Invalid buffer parameters");
        if (ADDR_W < ((DEPTH > 1) ? $clog2(DEPTH) : 1))
            $fatal(1, "Buffer address width cannot represent DEPTH");
    end
`endif
endmodule
