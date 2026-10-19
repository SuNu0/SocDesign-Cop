`timescale 1ns/1ps
module tb_linear_accel_top;
    parameter integer ROWS=2,INNER=64,COLS=2,JOBS=2,STALLS=1,TEST_FAULTS=1,INJECT_UNKNOWN_STATUS=0;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0,start=0;
    reg [3:0] layer_id=0;
    wire start_ready,busy,done,error,start_rejected;
    wire [3:0] active_layer,error_code;
    wire [31:0] completed_outputs,task_cycles;
    wire mem_req_valid,mem_req_write,mem_req_ready,mem_rsp_valid,mem_rsp_ready,mem_rsp_error;
    wire [1:0] mem_req_tensor;
    wire [31:0] mem_req_index;
    wire [63:0] mem_req_wdata,mem_rsp_rdata;
    wire mac_clear,mac_in_valid,mac_in_ready,mac_first,mac_last,mac_out_valid,mac_out_ready,mac_error;
    wire [15:0] mac_x,mac_w;
    wire [39:0] mac_bias,mac_result;
    reg job_begin=0,record_outputs=0;
    integer current_job=0,run_id=0,fault_mode=0,passed=0;
    reg [3:0] expected_layer=0;
    wire [31:0] acked_writes,read_x,read_w,read_b,write_y;
    wire inject_mac_error=(fault_mode==3 && mac_first) || (fault_mode==7 && mac_last);
    linear_accel_top #(.ROWS(ROWS),.INNER(INNER),.COLS(COLS)) dut(.*);
    dot_mac_model #(.INNER(INNER),.STALLS(STALLS)) u_mac (
        .clk(clk),.rst_n(rst_n),.clear(mac_clear),.inject_error(inject_mac_error),
        .in_valid(mac_in_valid),.in_ready(mac_in_ready),.x(mac_x),.w(mac_w),.bias(mac_bias),
        .first(mac_first),.last(mac_last),.out_valid(mac_out_valid),.out_ready(mac_out_ready),
        .result(mac_result),.error(mac_error));
    tensor_bus_model #(.ROWS(ROWS),.INNER(INNER),.COLS(COLS),.JOBS(JOBS),.STALLS(STALLS)) u_bus (
        .clk(clk),.rst_n(rst_n),.job_begin(job_begin),.record_outputs(record_outputs),
        .current_job(current_job),.run_id(run_id),.fault_mode(fault_mode),
        .req_valid(mem_req_valid),.req_write(mem_req_write),.req_ready(mem_req_ready),
        .req_tensor(mem_req_tensor),.req_index(mem_req_index),.req_wdata(mem_req_wdata),
        .rsp_valid(mem_rsp_valid),.rsp_ready(mem_rsp_ready),.rsp_rdata(mem_rsp_rdata),.rsp_error(mem_rsp_error),
        .acked_writes(acked_writes),.read_x(read_x),.read_w(read_w),.read_b(read_b),.write_y(write_y));

    // Check both request interfaces remain stable until accepted.
    reg previous_mem_stall=0,previous_mac_stall=0;
    reg [98:0] previous_mem_payload;
    reg [73:0] previous_mac_payload;
    reg previous_done=0;
    always @(posedge clk) begin
        if (!rst_n) begin previous_mem_stall<=0; previous_mac_stall<=0; end
        else begin
            // Reduction XOR also detects X/Z; avoids simulator-specific issues
            // with $isunknown called directly on concatenation expressions.
            if ((^{start_ready,busy,done,error,start_rejected,active_layer,error_code,
                            completed_outputs,task_cycles,mem_req_valid,mem_rsp_ready,mac_clear,
                            mac_in_valid,mac_out_ready}) === 1'bx)
                $fatal(1,"UNKNOWN_DUT_CONTROL flags=%b layer=%h code=%h count=%h cycles=%h",
                    {start_ready,busy,done,error,start_rejected,mem_req_valid,mem_rsp_ready,mac_clear,mac_in_valid,mac_out_ready},
                    active_layer,error_code,completed_outputs,task_cycles);
            if (busy && active_layer!==expected_layer) $fatal(1,"Accepted layer configuration changed while busy");
            if (mem_req_valid && ((^{mem_req_write,mem_req_tensor,mem_req_index,mem_req_wdata}) === 1'bx))
                $fatal(1,"UNKNOWN_MEMORY_REQUEST");
            if (mac_in_valid && ((^{mac_x,mac_w,mac_bias,mac_first,mac_last}) === 1'bx))
                $fatal(1,"UNKNOWN_MAC_REQUEST");
            if (previous_mem_stall && (!mem_req_valid || {mem_req_write,mem_req_tensor,mem_req_index,mem_req_wdata}!==previous_mem_payload))
                $fatal(1,"Memory request changed under backpressure");
            if (previous_mac_stall && !mac_clear && (!mac_in_valid || {mac_first,mac_last,mac_x,mac_w,mac_bias}!==previous_mac_payload))
                $fatal(1,"MAC request changed under backpressure");
            previous_mem_stall<=mem_req_valid && !mem_req_ready;
            previous_mac_stall<=mac_in_valid && !mac_in_ready;
            previous_mem_payload<={mem_req_write,mem_req_tensor,mem_req_index,mem_req_wdata};
            previous_mac_payload<={mac_first,mac_last,mac_x,mac_w,mac_bias};
        end
    end
    always @(negedge clk) begin
        if (!rst_n) previous_done<=0;
        else begin
            if (done===1'b1 && error!==1'b0) $fatal(1,"Invalid completion state");
            if (done && acked_writes!==ROWS*COLS) $fatal(1,"Early done before write acknowledgements");
            if (done && previous_done) $fatal(1,"done must be one cycle");
            previous_done<=done;
        end
    end
    task automatic begin_job(input integer job,input integer layer,input integer mode,input integer record_it);
        while (!start_ready) @(negedge clk);
        @(negedge clk);
        current_job=job; layer_id=layer[3:0]; expected_layer=layer[3:0]; fault_mode=mode; record_outputs=record_it;
        run_id=run_id+1; job_begin=1;
        @(negedge clk); job_begin=0; start=1;
        @(negedge clk); start=0;
    endtask
    task automatic success;
        while (!done && !error) @(negedge clk);
        if (done!==1'b1 || error!==1'b0) $fatal(1,"Invalid completion state code=%0d",error_code);
        if (completed_outputs!==ROWS*COLS || acked_writes!==ROWS*COLS || write_y!==ROWS*COLS)
            $fatal(1,"Output count mismatch");
        if (read_x!==ROWS*INNER || read_w!==INNER*COLS || read_b!==COLS)
            $fatal(1,"Unexpected load counts X=%0d W=%0d b=%0d",read_x,read_w,read_b);
        if (active_layer!==expected_layer) $fatal(1,"Layer configuration changed");
        passed=passed+1;
        $display("JOB_PASS run=%0d job=%0d layer=%0d cycles=%0d",run_id,current_job,active_layer,task_cycles);
        @(negedge clk);
    endtask
    task automatic expect_fault(input integer code,input integer committed);
        while (!done && !error) @(negedge clk);
        if (error!==1'b1 || done!==1'b0 || busy!==1'b0 || error_code!==code[3:0])
            $fatal(1,"Invalid error state expected=%0d got=%0d",code,error_code);
        if (acked_writes!==committed || completed_outputs!==committed)
            $fatal(1,"Fault test committed wrong output count");
        $display("FAULT_PASS code=%0d",code);
        @(negedge clk);
    endtask
    task automatic pulse_reset;
        @(negedge clk); start=0; rst_n=0;
        repeat (3) @(negedge clk);
        rst_n=1;
        @(negedge clk);
        if (busy!==1'b0 || done!==1'b0 || error!==1'b0 || start_ready!==1'b1)
            $fatal(1,"Reset did not return to idle");
    endtask
    initial begin
        if ($test$plusargs("dump")) begin $dumpfile("linear.vcd"); $dumpvars(0,tb_linear_accel_top); end
        repeat (3) @(negedge clk);
        rst_n=1;
        for (integer job=0;job<JOBS;job=job+1) begin
            begin_job(job,job%12,0,1);
            if (job==0) begin
                while (!mac_in_valid) @(negedge clk);
                layer_id=15; start=1; // Deliberately change external configuration.
                @(negedge clk); start=0;
                if (start_rejected!==1'b1 || active_layer!==expected_layer)
                    $fatal(1,"Busy start/configuration was not rejected");
            end
            success;
        end
        if (TEST_FAULTS) begin
            begin_job(0,0,1,0); expect_fault(1,0);
            begin_job(0,0,2,0); expect_fault(1,0);
            begin_job(0,0,3,0); expect_fault(3,0);
            begin_job(0,0,4,0); expect_fault(1,ROWS*COLS-1);
            begin_job(0,0,5,0); expect_fault(1,0);
            begin_job(0,0,6,0); expect_fault(1,0);
            begin_job(0,0,7,0); expect_fault(3,0);
            begin_job(0,15,0,0); expect_fault(2,0);
            if (read_x || read_w || read_b || write_y) $fatal(1,"Invalid layer accessed memory");
            // Abort an outstanding read response, then start from fresh state.
            begin_job(0,0,0,0);
            while (!(mem_req_valid && mem_req_ready)) @(negedge clk);
            pulse_reset;
            begin_job(0,0,0,1); success;
            begin_job(0,0,0,0);
            while (!mac_in_valid) @(negedge clk);
            pulse_reset;
            begin_job(0,0,0,1); success;
            // Abort with a write waiting for acknowledgement, then recover.
            begin_job(0,1,0,0);
            while (!(mem_req_valid && mem_req_ready && mem_req_write)) @(negedge clk);
            @(negedge clk);
            pulse_reset;
            begin_job(0,1,0,1); success;
            $display("RESET_RECOVERY_PASS");
        end
        $display("B_REGRESSION_PASS jobs=%0d rows=%0d inner=%0d cols=%0d",passed,ROWS,INNER,COLS);
        $finish;
    end
    generate
        if (INJECT_UNKNOWN_STATUS==1) begin: g_unknown_done
            initial begin wait(done); force error=1'bx; end
        end else if (INJECT_UNKNOWN_STATUS==2) begin: g_unknown_error
            initial begin wait(error); force error_code=4'bxxxx; end
        end
    endgenerate
    initial begin
        #2000000000;
        $fatal(1,"Regression watchdog timeout");
    end
endmodule
