`timescale 1ns/1ps
// Fixed-shape FFN first-linear-layer accelerator, 99x64 * 64x256 + bias.
// ICB-style, one outstanding transaction, word-aligned local byte addresses.
// See README for register map and the exact Q8.8 numerical contract.
module ffn_accel (
  input  wire         clk,
  input  wire         rst_n,
  input  wire         i_icb_cmd_valid,
  output wire         o_icb_cmd_ready,
  input  wire         i_icb_cmd_read,
  input  wire [31:0]  i_icb_cmd_addr,
  input  wire [31:0]  i_icb_cmd_wdata,
  input  wire [3:0]   i_icb_cmd_wmask,
  output logic        o_icb_rsp_valid,
  input  wire         i_icb_rsp_ready,
  output logic [31:0] o_icb_rsp_rdata,
  output logic        o_icb_rsp_err,
  output wire         o_irq
);
  import ffn_numeric_pkg::*;
  localparam integer ROWS=99, INNER=64, COLS=256, LANES=16;
  localparam [31:0] X_BASE=32'h0001_0000, X_LIMIT=32'h0001_6300;
  localparam [31:0] W_BASE=32'h0002_0000, W_LIMIT=32'h0003_0000;
  localparam [31:0] B_BASE=32'h0003_0000, B_LIMIT=32'h0003_0400;
  localparam [31:0] Y_BASE=32'h0004_0000, Y_LIMIT=32'h0005_8c00;
  localparam [2:0] MEM_NONE=0, MEM_X=1, MEM_W=2, MEM_B=3, MEM_Y=4;

  typedef enum logic [2:0] {S_IDLE,S_BIAS,S_MAC,S_ROUND,S_WRITE} state_t;
  typedef enum logic [1:0] {H_IDLE,H_READ,H_RESPONSE} host_state_t;
  state_t state;
  host_state_t host_state;
  wire busy = (state != S_IDLE);
  logic done;
  logic [31:0] cycle_count, saturation_count;
  logic [3:0] layer_tag;
  assign o_irq=done;
  assign o_icb_cmd_ready=rst_n && (host_state==H_IDLE);
  wire accept=i_icb_cmd_valid && o_icb_cmd_ready;

  logic dec_error;
  logic [2:0] dec_mem;
  logic [31:0] dec_index, dec_rdata;
  always @* begin
    dec_error=1'b0; dec_mem=MEM_NONE; dec_index=0; dec_rdata=0;
    if (i_icb_cmd_addr[1:0] != 0) dec_error=1'b1;
    else if (!i_icb_cmd_read && i_icb_cmd_wmask != 4'hf) dec_error=1'b1;
    else if (i_icb_cmd_addr>=X_BASE && i_icb_cmd_addr<X_LIMIT) begin
      dec_mem=MEM_X; dec_index=(i_icb_cmd_addr-X_BASE)>>2;
    end else if (i_icb_cmd_addr>=W_BASE && i_icb_cmd_addr<W_LIMIT) begin
      dec_mem=MEM_W; dec_index=(i_icb_cmd_addr-W_BASE)>>2;
    end else if (i_icb_cmd_addr>=B_BASE && i_icb_cmd_addr<B_LIMIT) begin
      dec_mem=MEM_B; dec_index=(i_icb_cmd_addr-B_BASE)>>2;
    end else if (i_icb_cmd_addr>=Y_BASE && i_icb_cmd_addr<Y_LIMIT) begin
      dec_mem=MEM_Y; dec_index=(i_icb_cmd_addr-Y_BASE)>>2;
      if (!i_icb_cmd_read) dec_error=1'b1;
    end else begin
      case (i_icb_cmd_addr)
        32'h00: begin
          if (!i_icb_cmd_read &&
              ((i_icb_cmd_wdata & 32'hffff_fffc)!=0 ||
               (i_icb_cmd_wdata[0] && busy))) dec_error=1'b1;
        end
        32'h04: begin dec_rdata={30'd0,done,busy}; if (!i_icb_cmd_read) dec_error=1'b1; end
        32'h08: begin dec_rdata=cycle_count; if (!i_icb_cmd_read) dec_error=1'b1; end
        32'h0c: begin dec_rdata=32'd1622016; if (!i_icb_cmd_read) dec_error=1'b1; end
        32'h10: begin dec_rdata=ROWS; if (!i_icb_cmd_read) dec_error=1'b1; end
        32'h14: begin dec_rdata=INNER; if (!i_icb_cmd_read) dec_error=1'b1; end
        32'h18: begin dec_rdata=COLS; if (!i_icb_cmd_read) dec_error=1'b1; end
        32'h1c: begin dec_rdata=32'h0000_0810; if (!i_icb_cmd_read) dec_error=1'b1; end
        32'h20: begin
          dec_rdata={28'd0,layer_tag};
          if (!i_icb_cmd_read && (busy || i_icb_cmd_wdata>11)) dec_error=1'b1;
        end
        32'h24: begin dec_rdata=saturation_count; if (!i_icb_cmd_read) dec_error=1'b1; end
        32'h28: begin dec_rdata=32'h0001_0000; if (!i_icb_cmd_read) dec_error=1'b1; end
        default: dec_error=1'b1;
      endcase
    end
    // Single-port memories are exclusively owned by the core during a task.
    if (dec_mem!=MEM_NONE && busy) dec_error=1'b1;
  end
  wire host_mem=accept && !dec_error && dec_mem!=MEM_NONE;
  wire start_event=accept && !dec_error && !i_icb_cmd_read &&
                   i_icb_cmd_addr==0 && i_icb_cmd_wdata[0];
  wire clear_done=accept && !dec_error && !i_icb_cmd_read &&
                  i_icb_cmd_addr==0 && i_icb_cmd_wdata[1];

  logic [6:0] row_index;
  logic [3:0] group_index, write_lane, bias_lane_d;
  logic [4:0] bias_issue;
  logic [6:0] mac_issue;
  logic bias_valid, mac_read_valid, mac_read_last, product_valid, product_last;
  logic signed [31:0] product [0:LANES-1];
  logic signed [39:0] accumulator [0:LANES-1];
  logic [15:0] output_buffer [0:LANES-1];
  wire [16:0] quantized [0:LANES-1];
  logic [4:0] saturation_increment;
  for (genvar q=0;q<LANES;q=q+1) begin: gen_quantize
    assign quantized[q]=requantize(accumulator[q]);
  end
  always @* begin
    saturation_increment=0;
    for (integer s=0;s<LANES;s=s+1)
      saturation_increment=saturation_increment+{4'd0,quantized[s][16]};
  end

  logic x_en,x_we,b_en,b_we,y_en,y_we;
  logic [12:0] x_addr;
  logic [7:0] b_addr;
  logic [14:0] y_addr;
  logic [15:0] y_wdata;
  wire [15:0] x_rdata,b_rdata,y_rdata;
  logic [LANES-1:0] w_en,w_we;
  logic [9:0] w_addr [0:LANES-1];
  wire [15:0] w_rdata [0:LANES-1];

  always @* begin
    x_en=0; x_we=0; x_addr=0;
    b_en=0; b_we=0; b_addr=0;
    y_en=0; y_we=0; y_addr=0; y_wdata=0;
    w_en=0; w_we=0;
    for (integer a=0;a<LANES;a=a+1) w_addr[a]=0;
    if (state==S_BIAS && bias_issue<16) begin
      b_en=1; b_addr={group_index,bias_issue[3:0]};
    end
    if (state==S_MAC && mac_issue<64) begin
      x_en=1; x_addr={row_index,mac_issue[5:0]};
      w_en=16'hffff;
      for (integer a=0;a<LANES;a=a+1)
        w_addr[a]={mac_issue[5:0],group_index};
    end
    if (state==S_WRITE) begin
      y_en=1; y_we=1;
      y_addr={row_index,group_index,write_lane};
      y_wdata=output_buffer[write_lane];
    end
    if (host_mem) begin
      case (dec_mem)
        MEM_X: begin x_en=1; x_we=!i_icb_cmd_read; x_addr=dec_index[12:0]; end
        MEM_W: begin
          w_en[dec_index[3:0]]=1;
          w_we[dec_index[3:0]]=!i_icb_cmd_read;
          w_addr[dec_index[3:0]]=dec_index[13:4];
        end
        MEM_B: begin b_en=1; b_we=!i_icb_cmd_read; b_addr=dec_index[7:0]; end
        MEM_Y: begin y_en=1; y_addr=dec_index[14:0]; end
        default: begin end
      endcase
    end
  end
  ffn_banked_sram #(.DEPTH(6336),.BANK_DEPTH(4096)) u_x (
    .clk(clk),.en(x_en),.we(x_we),.addr(x_addr),
    .wdata(i_icb_cmd_wdata[15:0]),.rdata(x_rdata)
  );
  ffn_banked_sram #(.DEPTH(256),.BANK_DEPTH(128)) u_bias (
    .clk(clk),.en(b_en),.we(b_we),.addr(b_addr),
    .wdata(i_icb_cmd_wdata[15:0]),.rdata(b_rdata)
  );
  ffn_banked_sram #(.DEPTH(25344),.BANK_DEPTH(4096)) u_y (
    .clk(clk),.en(y_en),.we(y_we),.addr(y_addr),.wdata(y_wdata),.rdata(y_rdata)
  );
  for (genvar w=0;w<LANES;w=w+1) begin: gen_weight
    // bank=j%16; local_address=k*16+j/16. All 16 banks read together.
    ffn_sram_1rw #(.DEPTH(1024)) u_mem (
      .clk(clk),.en(w_en[w]),.we(w_we[w]),.addr(w_addr[w]),
      .wdata(i_icb_cmd_wdata[15:0]),.rdata(w_rdata[w])
    );
  end

  logic [2:0] host_read_mem;
  logic [3:0] host_read_bank;
  logic [15:0] host_read_word;
  always @* begin
    case (host_read_mem)
      MEM_X: host_read_word=x_rdata;
      MEM_W: host_read_word=w_rdata[host_read_bank];
      MEM_B: host_read_word=b_rdata;
      MEM_Y: host_read_word=y_rdata;
      default: host_read_word=0;
    endcase
  end
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      host_state<=H_IDLE; o_icb_rsp_valid<=0;
      o_icb_rsp_rdata<=0; o_icb_rsp_err<=0;
      host_read_mem<=MEM_NONE; host_read_bank<=0; layer_tag<=0;
    end else begin
      case (host_state)
        H_IDLE: if (accept) begin
          o_icb_rsp_rdata<=0; o_icb_rsp_err<=dec_error;
          if (!dec_error && dec_mem!=MEM_NONE && i_icb_cmd_read) begin
            host_read_mem<=dec_mem; host_read_bank<=dec_index[3:0];
            host_state<=H_READ;
          end else begin
            o_icb_rsp_rdata<=dec_error ? 32'd0 : dec_rdata;
            o_icb_rsp_valid<=1; host_state<=H_RESPONSE;
          end
          if (!dec_error && !i_icb_cmd_read && i_icb_cmd_addr==32'h20)
            layer_tag<=i_icb_cmd_wdata[3:0];
        end
        H_READ: begin
          o_icb_rsp_rdata<={{16{host_read_word[15]}},host_read_word};
          o_icb_rsp_valid<=1; host_state<=H_RESPONSE;
        end
        H_RESPONSE: if (i_icb_rsp_ready) begin
          o_icb_rsp_valid<=0; host_state<=H_IDLE;
        end
        default: begin host_state<=H_IDLE; o_icb_rsp_valid<=0; end
      endcase
    end
  end

  integer lane;
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      state<=S_IDLE; done<=0; cycle_count<=0; saturation_count<=0;
      row_index<=0; group_index<=0; write_lane<=0;
      bias_issue<=0; bias_valid<=0; bias_lane_d<=0;
      mac_issue<=0; mac_read_valid<=0; mac_read_last<=0;
      product_valid<=0; product_last<=0;
      for (lane=0;lane<LANES;lane=lane+1) begin
        accumulator[lane]<=0; product[lane]<=0; output_buffer[lane]<=0;
      end
    end else begin
      if (clear_done) done<=0;
      if (busy) cycle_count<=cycle_count+1;
      case (state)
        S_IDLE: if (start_event) begin
          done<=0; cycle_count<=0; saturation_count<=0;
          row_index<=0; group_index<=0; write_lane<=0;
          bias_issue<=0; bias_valid<=0; mac_issue<=0;
          mac_read_valid<=0; product_valid<=0;
          state<=S_BIAS;
        end
        S_BIAS: begin
          // 16 synchronous bias reads + one drain cycle. Bias is aligned to Q16.
          bias_valid<=(bias_issue<16);
          if (bias_issue<16) begin
            bias_lane_d<=bias_issue[3:0]; bias_issue<=bias_issue+1;
          end
          if (bias_valid) begin
            accumulator[bias_lane_d]<=
              $signed({{24{b_rdata[15]}},b_rdata}) <<< 8;
            if (bias_lane_d==15) begin
              mac_issue<=0; mac_read_valid<=0; mac_read_last<=0;
              product_valid<=0; product_last<=0; state<=S_MAC;
            end
          end
        end
        S_MAC: begin
          // SRAM read -> registered 16x16 products -> 40-bit accumulation.
          mac_read_valid<=(mac_issue<64);
          mac_read_last<=(mac_issue==63);
          if (mac_issue<64) mac_issue<=mac_issue+1;
          product_valid<=mac_read_valid; product_last<=mac_read_last;
          if (mac_read_valid)
            for (lane=0;lane<LANES;lane=lane+1)
              product[lane]<=$signed(x_rdata)*$signed(w_rdata[lane]);
          if (product_valid)
            for (lane=0;lane<LANES;lane=lane+1)
              accumulator[lane]<=accumulator[lane]+
                $signed({{8{product[lane][31]}},product[lane]});
          if (product_valid && product_last) state<=S_ROUND;
        end
        S_ROUND: begin
          for (lane=0;lane<LANES;lane=lane+1)
            output_buffer[lane]<=quantized[lane][15:0];
          saturation_count<=saturation_count+{27'd0,saturation_increment};
          write_lane<=0; state<=S_WRITE;
        end
        S_WRITE: begin
          if (write_lane==15) begin
            if (group_index==15 && row_index==98) begin
              done<=1; state<=S_IDLE;
            end else begin
              if (group_index==15) begin group_index<=0; row_index<=row_index+1; end
              else group_index<=group_index+1;
              bias_issue<=0; bias_valid<=0; state<=S_BIAS;
            end
          end else write_lane<=write_lane+1;
        end
        default: state<=S_IDLE;
      endcase
    end
  end
endmodule