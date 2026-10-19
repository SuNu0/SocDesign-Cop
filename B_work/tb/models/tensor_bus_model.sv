`timescale 1ns/1ps
// TEST ONLY. Logical tensor/element protocol, not System Bus or NICE.
module tensor_bus_model #(
    parameter integer ROWS=99,INNER=64,COLS=256,JOBS=2,STALLS=1,
    parameter integer RESULT_W=40
) (
    input wire clk,rst_n,job_begin,record_outputs,
    input integer current_job,run_id,fault_mode,
    input wire req_valid,req_write,
    output wire req_ready,
    input wire [1:0] req_tensor,
    input wire [31:0] req_index,
    input wire [63:0] req_wdata,
    output reg rsp_valid,
    input wire rsp_ready,
    output reg [63:0] rsp_rdata,
    output reg rsp_error,
    output reg [31:0] acked_writes,read_x,read_w,read_b,write_y
);
    reg [15:0] input_x[0:JOBS*ROWS*INNER-1];
    reg [15:0] input_w[0:JOBS*INNER*COLS-1];
    reg [39:0] input_b[0:JOBS*COLS-1];
    reg [RESULT_W-1:0] expected[0:JOBS*ROWS*COLS-1];
    reg seen_y[0:ROWS*COLS-1];
    reg [31:0] random_state;
    reg pending,pending_write,pending_error;
    reg [63:0] pending_data;
    reg [31:0] pending_index;
    integer delay_count,fd;
    assign req_ready=rst_n && !pending && !rsp_valid && (!STALLS || random_state[1] || random_state[4]);
    initial begin
        if (RESULT_W<1 || RESULT_W>64) $fatal(1,"Invalid tensor bus model result width");
        $readmemh("x.hex",input_x);
        $readmemh("w.hex",input_w);
        $readmemh("b.hex",input_b);
        $readmemh("expected.hex",expected);
        fd=$fopen("observed.txt","w");
        if (!fd) $fatal(1,"Cannot create observed.txt");
    end
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            random_state<=32'h94ac3217; pending<=0; pending_write<=0; pending_error<=0;
            pending_data<=0; pending_index<=0; delay_count<=0;
            rsp_valid<=0; rsp_rdata<=0; rsp_error<=0;
            acked_writes<=0; read_x<=0; read_w<=0; read_b<=0; write_y<=0;
            for (integer i=0;i<ROWS*COLS;i=i+1) seen_y[i]<=0;
        end else begin
            random_state<={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
            if (job_begin) begin
                if (pending || rsp_valid) $fatal(1,"New test job with outstanding transaction");
                acked_writes<=0; read_x<=0; read_w<=0; read_b<=0; write_y<=0;
                for (integer i=0;i<ROWS*COLS;i=i+1) seen_y[i]<=0;
            end
            if (rsp_valid && rsp_ready) begin
                rsp_valid<=0;
                if (pending_write && !rsp_error) begin
                    acked_writes<=acked_writes+1;
                    if (record_outputs)
                        $fdisplay(fd,"%0d %0d %0d %010h",run_id,current_job,pending_index,pending_data[RESULT_W-1:0]);
                end
                pending_write<=0;
            end
            if (pending) begin
                if (delay_count==0) begin
                    pending<=0; rsp_valid<=1; rsp_rdata<=pending_data; rsp_error<=pending_error;
                end else delay_count<=delay_count-1;
            end
            if (req_valid && req_ready) begin
                pending<=1; pending_write<=req_write; pending_index<=req_index;
                pending_error<=0;
                delay_count<=STALLS ? {29'd0,random_state[7:5]} : 0;
                if (req_write) begin
                    if (req_tensor!=3 || req_index>=ROWS*COLS) $fatal(1,"Invalid write request");
                    if (req_index!==write_y) $fatal(1,"Output order mismatch");
                    if (seen_y[req_index]) $fatal(1,"Duplicate output index=%0d",req_index);
                    if ((req_wdata >> RESULT_W)!==64'd0 || req_wdata[RESULT_W-1:0]!==expected[current_job*ROWS*COLS+req_index])
                        $fatal(1,"Output mismatch job=%0d index=%0d got=%h expected=%h",current_job,req_index,req_wdata[RESULT_W-1:0],expected[current_job*ROWS*COLS+req_index]);
                    seen_y[req_index]<=1;
                    pending_data<=req_wdata;
                    write_y<=write_y+1;
                    if (req_index==ROWS*COLS-1) delay_count<=17; // Force final-ack wait.
                    if (fault_mode==2 && req_index==0) pending_error<=1;
                    if (fault_mode==4 && req_index==ROWS*COLS-1) pending_error<=1;
                end else begin
                    case (req_tensor)
                        0: begin
                            if (req_index>=ROWS*INNER) $fatal(1,"X index out of range");
                            pending_data<={48'd0,input_x[current_job*ROWS*INNER+req_index]};
                            read_x<=read_x+1;
                            if (fault_mode==6 && req_index==INNER-1) pending_error<=1;
                        end
                        1: begin
                            if (req_index>=INNER*COLS) $fatal(1,"W index out of range");
                            pending_data<={48'd0,input_w[current_job*INNER*COLS+req_index]};
                            read_w<=read_w+1;
                            if (fault_mode==1 && req_index==((INNER*COLS>7)?7:0)) pending_error<=1;
                        end
                        2: begin
                            if (req_index>=COLS) $fatal(1,"Bias index out of range");
                            pending_data<={24'd0,input_b[current_job*COLS+req_index]};
                            read_b<=read_b+1;
                            if (fault_mode==5 && req_index==0) pending_error<=1;
                        end
                        default: $fatal(1,"Invalid tensor read");
                    endcase
                end
            end
        end
    end
endmodule
