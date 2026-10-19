`timescale 1ns/1ps
package ffn_numeric_pkg;
  // Signed 16-bit values encode real_value * 256 (eight fractional bits).
  localparam integer DATA_W = 16;
  localparam integer FRAC_W = 8;
  localparam integer ACC_W  = 40;

  // Return {saturated, signed_result[15:0]}.
  // One rounding operation after the full dot product AND bias addition.
  // Round to nearest, ties away from zero, then saturate to [-32768,32767].
  function automatic logic [16:0] requantize(input logic signed [39:0] acc);
    logic signed [40:0] wide_value;
    logic signed [40:0] magnitude;
    logic signed [40:0] rounded;
    begin
      wide_value = {acc[39], acc};
      if (wide_value < 0) begin
        magnitude = -wide_value;
        rounded = -((magnitude + 41'sd128) >>> 8);
      end else begin
        rounded = (wide_value + 41'sd128) >>> 8;
      end
      if (rounded > 41'sd32767)
        requantize = {1'b1, 16'h7fff};
      else if (rounded < -41'sd32768)
        requantize = {1'b1, 16'h8000};
      else
        requantize = {1'b0, rounded[15:0]};
    end
  endfunction
endpackage
