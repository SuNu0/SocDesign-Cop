`timescale 1ns/1ps
// One 16-bit single-port macro. Default backend is a portable behavioral model.
// Define B_USE_OFFICIAL_SRAM only after supplying the three real adapters.
module sram_wrapper #(
    parameter integer DEPTH = 4096,
    parameter integer AW = $clog2(DEPTH)
) (
    input wire clk,
    input wire en,
    input wire we,
    input wire [AW-1:0] addr,
    input wire [15:0] wdata,
    output wire [15:0] rdata
);
`ifdef B_USE_OFFICIAL_SRAM
    generate
        if (DEPTH == 128) begin: g128
            b_official_sram_16x128 u_macro(.*);
        end else if (DEPTH == 1024) begin: g1024
            b_official_sram_16x1024 u_macro(.*);
        end else if (DEPTH == 4096) begin: g4096
            b_official_sram_16x4096 u_macro(.*);
        end
    endgenerate
`else
    reg [15:0] mem [0:DEPTH-1];
    reg [15:0] read_value;
    assign rdata = read_value;
    always @(posedge clk) begin
        if (en) begin
            if (we) mem[addr] <= wdata;
            else read_value <= mem[addr];
        end
    end
`endif
`ifndef SYNTHESIS
    initial begin
        if (DEPTH != 128 && DEPTH != 1024 && DEPTH != 4096)
            $fatal(1, "Unsupported macro geometry");
        if (AW != $clog2(DEPTH))
            $fatal(1, "SRAM address width must match DEPTH");
    end
`endif
endmodule
