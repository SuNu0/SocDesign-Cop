`timescale 1ns/1ps
// Synthesizable single-port synchronous SRAM abstraction. No array reset.
// Replace the body with the supplied 16 x 128/1024/4096 SRAM macro at integration.
// Read data updates on an enabled READ edge; writes leave read data unchanged.
module ffn_sram_1rw #(
  parameter integer DEPTH = 1024,
  parameter integer ADDR_W = $clog2(DEPTH)
) (
  input  wire              clk,
  input  wire              en,
  input  wire              we,
  input  wire [ADDR_W-1:0]  addr,
  input  wire [15:0]        wdata,
  output logic [15:0]       rdata
);
  logic [15:0] mem [0:DEPTH-1];
  always_ff @(posedge clk) begin
    if (en) begin
      if (we) mem[addr] <= wdata;
      else    rdata <= mem[addr];
    end
  end
endmodule

// Several allowed power-of-two macros form one logical single-port memory.
module ffn_banked_sram #(
  parameter integer DEPTH = 6336,
  parameter integer BANK_DEPTH = 4096,
  parameter integer ADDR_W = $clog2(DEPTH),
  parameter integer BANK_AW = $clog2(BANK_DEPTH),
  parameter integer BANKS = (DEPTH+BANK_DEPTH-1)/BANK_DEPTH,
  parameter integer SEL_W = (BANKS <= 1) ? 1 : $clog2(BANKS)
) (
  input  wire              clk,
  input  wire              en,
  input  wire              we,
  input  wire [ADDR_W-1:0]  addr,
  input  wire [15:0]        wdata,
  output wire [15:0]       rdata
);
  wire [15:0] bank_rdata [0:BANKS-1];
  wire [SEL_W-1:0] bank_select = addr >> BANK_AW;
  logic [SEL_W-1:0] read_select;
  always_ff @(posedge clk) begin
    if (en && !we) read_select <= bank_select;
  end
  for (genvar g=0; g<BANKS; g=g+1) begin: gen_bank
    localparam integer BANK_INDEX=g;
    ffn_sram_1rw #(.DEPTH(BANK_DEPTH)) u_mem (
      .clk(clk), .en(en && bank_select == BANK_INDEX), .we(we),
      .addr(addr[BANK_AW-1:0]), .wdata(wdata), .rdata(bank_rdata[BANK_INDEX])
    );
  end
  assign rdata = bank_rdata[read_select];
endmodule
