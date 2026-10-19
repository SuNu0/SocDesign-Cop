`timescale 1ns/1ps
// Real A + B integration. Inputs and expected values come from A's numerical
// model; tensor_bus_model supplies only the external tensor transport.
module tb_linear_accel_a_top;
    parameter integer ROWS=3,COLS=5,JOBS=12,STALLS=1,TEST_FAULTS=1;
    localparam integer INNER=64,BUS_W=64;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0,start=0;
    reg [3:0] layer_id=0;
    reg [5:0] task_shift=0;
    wire start_ready,busy,done,error,start_rejected;
    wire [3:0] active_layer,error_code;
    wire [5:0] active_shift;
    wire [31:0] completed_outputs,task_cycles;
    wire mem_req_valid,mem_req_write,mem_req_ready,mem_rsp_valid,mem_rsp_ready,mem_rsp_error;
    wire [1:0] mem_req_tensor;
    wire [31:0] mem_req_index;
    wire [BUS_W-1:0] mem_req_wdata,mem_rsp_rdata;
    reg job_begin=0,record_outputs=0;
    integer current_job=0,run_id=0,fault_mode=0,passed=0;
    reg [3:0] job_layers[0:JOBS-1];
    reg [5:0] job_shifts[0:JOBS-1];
    reg [3:0] expected_layer=0;
    reg [5:0] expected_shift=0;
    wire [31:0] acked_writes,read_x,read_w,read_b,write_y;

    linear_accel_a_top #(.ROWS(ROWS),.COLS(COLS),.BUS_W(BUS_W)) dut(.*);
    tensor_bus_model #(.ROWS(ROWS),.INNER(INNER),.COLS(COLS),.JOBS(JOBS),
        .STALLS(STALLS),.RESULT_W(16)) u_bus (
        .clk(clk),.rst_n(rst_n),.job_begin(job_begin),.record_outputs(record_outputs),
        .current_job(current_job),.run_id(run_id),.fault_mode(fault_mode),
        .req_valid(mem_req_valid),.req_write(mem_req_write),.req_ready(mem_req_ready),
        .req_tensor(mem_req_tensor),.req_index(mem_req_index),.req_wdata(mem_req_wdata),
        .rsp_valid(mem_rsp_valid),.rsp_ready(mem_rsp_ready),.rsp_rdata(mem_rsp_rdata),.rsp_error(mem_rsp_error),
        .acked_writes(acked_writes),.read_x(read_x),.read_w(read_w),.read_b(read_b),.write_y(write_y));

    reg previous_mem_stall=0,previous_mac_stall=0,previous_result_stall=0;
    reg [98:0] previous_mem_payload;
    reg [73:0] previous_mac_payload;
    reg [15:0] previous_mac_result;
    reg [39:0] dot_bias;
    integer accepted_terms=0;
    reg previous_done=0;

    always @(posedge clk) begin
        if (!rst_n) begin
            previous_mem_stall<=0;
            previous_mac_stall<=0;
            previous_result_stall<=0;
            accepted_terms=0;
        end else begin
            // Reduction XOR detects X/Z without the Icarus concatenation issue
            // seen with $isunknown on some development versions.
            if ((^{start_ready,busy,done,error,start_rejected,active_layer,active_shift,
                    error_code,completed_outputs,task_cycles,mem_req_valid,mem_rsp_ready,
                    dut.mac_clear,dut.mac_in_valid,dut.mac_in_ready,dut.mac_out_valid,
                    dut.mac_out_ready,dut.mac_error}) === 1'bx)
                $fatal(1,"AB_UNKNOWN_CONTROL");
            if (busy && (active_layer!==expected_layer || active_shift!==expected_shift))
                $fatal(1,"AB accepted task configuration changed while busy");
            if (mem_req_valid && ((^{mem_req_write,mem_req_tensor,mem_req_index,mem_req_wdata}) === 1'bx))
                $fatal(1,"AB_UNKNOWN_MEMORY_REQUEST");
            if (dut.mac_in_valid && ((^{dut.mac_x,dut.mac_w,dut.mac_bias,dut.mac_first,dut.mac_last}) === 1'bx))
                $fatal(1,"AB_UNKNOWN_MAC_REQUEST");
            if (dut.mac_out_valid && ((^dut.mac_result) === 1'bx))
                $fatal(1,"AB_UNKNOWN_MAC_RESULT");
            if (previous_mem_stall && (!mem_req_valid ||
                    {mem_req_write,mem_req_tensor,mem_req_index,mem_req_wdata}!==previous_mem_payload))
                $fatal(1,"AB memory request changed under backpressure");
            if (previous_mac_stall && !dut.mac_clear && (!dut.mac_in_valid ||
                    {dut.mac_first,dut.mac_last,dut.mac_x,dut.mac_w,dut.mac_bias}!==previous_mac_payload))
                $fatal(1,"AB MAC request changed under backpressure");
            if (previous_result_stall && !dut.mac_clear && (!dut.mac_out_valid ||
                    dut.mac_result!==previous_mac_result))
                $fatal(1,"AB MAC result changed under backpressure");
            previous_mem_stall<=mem_req_valid && !mem_req_ready;
            previous_mac_stall<=dut.mac_in_valid && !dut.mac_in_ready;
            previous_result_stall<=dut.mac_out_valid && !dut.mac_out_ready;
            previous_mem_payload<={mem_req_write,mem_req_tensor,mem_req_index,mem_req_wdata};
            previous_mac_payload<={dut.mac_first,dut.mac_last,dut.mac_x,dut.mac_w,dut.mac_bias};
            previous_mac_result<=dut.mac_result;

            if (dut.mac_clear) accepted_terms=0;
            else begin
                if (dut.mac_in_valid && dut.mac_in_ready) begin
                    if (dut.mac_first!==(accepted_terms==0) || dut.mac_last!==(accepted_terms==INNER-1))
                        $fatal(1,"AB dot-product boundary/count mismatch terms=%0d",accepted_terms);
                    if (accepted_terms==0) dot_bias=dut.mac_bias;
                    else if (dut.mac_bias!==dot_bias) $fatal(1,"AB bias changed during a dot product");
                    accepted_terms=accepted_terms+1;
                end
                if (dut.mac_out_valid && dut.mac_out_ready) begin
                    if (accepted_terms!=INNER) $fatal(1,"AB result before all 64 operands were accepted");
                    accepted_terms=0;
                end
            end
        end
    end

    always @(negedge clk) begin
        if (!rst_n) previous_done<=0;
        else begin
            if (done===1'b1 && error!==1'b0) $fatal(1,"AB invalid completion state");
            if (done && acked_writes!==ROWS*COLS) $fatal(1,"AB early done before write acknowledgements");
            if (done && previous_done) $fatal(1,"AB done must be one cycle");
            previous_done<=done;
        end
    end

    task automatic begin_job(input integer job,input integer layer,input integer mode,input integer record_it);
        while (start_ready!==1'b1) @(negedge clk);
        @(negedge clk);
        current_job=job;
        layer_id=layer[3:0]; expected_layer=layer[3:0];
        task_shift=job_shifts[job]; expected_shift=job_shifts[job];
        fault_mode=mode; record_outputs=record_it;
        run_id=run_id+1; job_begin=1;
        @(negedge clk); job_begin=0; start=1;
        @(negedge clk); start=0;
    endtask

    task automatic success;
        while (!done && !error) @(negedge clk);
        if (done!==1'b1 || error!==1'b0) $fatal(1,"AB invalid completion code=%0d",error_code);
        if (completed_outputs!==ROWS*COLS || acked_writes!==ROWS*COLS || write_y!==ROWS*COLS)
            $fatal(1,"AB output count mismatch");
        if (read_x!==ROWS*INNER || read_w!==INNER*COLS || read_b!==COLS)
            $fatal(1,"AB unexpected load counts X=%0d W=%0d b=%0d",read_x,read_w,read_b);
        if (active_layer!==expected_layer || active_shift!==expected_shift)
            $fatal(1,"AB task configuration mismatch at completion");
        passed=passed+1;
        $display("AB_JOB_PASS run=%0d job=%0d layer=%0d shift=%0d cycles=%0d",
            run_id,current_job,active_layer,active_shift,task_cycles);
        @(negedge clk);
    endtask

    task automatic expect_fault(input integer code,input integer committed);
        while (!done && !error) @(negedge clk);
        if (error!==1'b1 || done!==1'b0 || busy!==1'b0 || error_code!==code[3:0])
            $fatal(1,"AB invalid error state expected=%0d got=%0d",code,error_code);
        if (acked_writes!==committed || completed_outputs!==committed)
            $fatal(1,"AB fault test committed wrong output count");
        $display("AB_FAULT_PASS code=%0d",code);
        @(negedge clk);
    endtask

    task automatic pulse_reset;
        @(negedge clk); start=0; rst_n=0;
        repeat (3) @(negedge clk);
        rst_n=1;
        @(negedge clk);
        if (busy!==1'b0 || done!==1'b0 || error!==1'b0 || start_ready!==1'b1)
            $fatal(1,"AB reset did not return to idle");
    endtask

    task automatic wait_mac_request;
        while (dut.mac_in_valid!==1'b1) begin
            if (error) $fatal(1,"AB unexpected failure before MAC input");
            @(negedge clk);
        end
    endtask

    integer partial_terms;
    initial begin
        if (ROWS<1 || COLS<1 || JOBS<1) $fatal(1,"AB invalid test dimensions");
        $readmemh("job_layers.hex",job_layers);
        $readmemh("job_shifts.hex",job_shifts);
        for (integer job=0;job<JOBS;job=job+1) begin
            if ((^job_layers[job])===1'bx || job_layers[job]>=12 || (^job_shifts[job])===1'bx)
                $fatal(1,"AB invalid/missing job metadata index=%0d",job);
        end
        if ($test$plusargs("dump")) begin $dumpfile("linear_ab.vcd"); $dumpvars(0,tb_linear_accel_a_top); end
        repeat (3) @(negedge clk);
        rst_n=1;
        for (integer job=0;job<JOBS;job=job+1) begin
            begin_job(job,job_layers[job],0,1);
            if (job==0) begin
                wait_mac_request;
                layer_id=15; task_shift=expected_shift^6'h3f; start=1;
                @(negedge clk); start=0;
                if (start_rejected!==1'b1 || active_layer!==expected_layer || active_shift!==expected_shift)
                    $fatal(1,"AB busy start/configuration was not rejected");
            end
            success;
        end
        if (TEST_FAULTS) begin
            begin_job(0,job_layers[0],1,0); expect_fault(1,0);
            begin_job(0,job_layers[0],2,0); expect_fault(1,0);
            begin_job(0,job_layers[0],4,0); expect_fault(1,ROWS*COLS-1);
            begin_job(0,job_layers[0],5,0); expect_fault(1,0);
            begin_job(0,job_layers[0],6,0); expect_fault(1,0);
            begin_job(0,15,0,0); expect_fault(2,0);
            if (read_x || read_w || read_b || write_y) $fatal(1,"AB invalid layer accessed memory");

            // Abort an accepted read before its response is consumed.
            begin_job(0,job_layers[0],0,0);
            while (!(mem_req_valid && mem_req_ready)) @(negedge clk);
            pulse_reset;
            begin_job(0,job_layers[0],0,1); success;

            // Reset the real A lane after seven accepted pairs, not just before
            // its first input. This checks that partial accumulation is cleared.
            begin_job(0,job_layers[0],0,0);
            partial_terms=0;
            while (partial_terms<7) begin
                @(posedge clk);
                if (error) $fatal(1,"AB unexpected failure before partial-dot reset");
                if (dut.mac_in_valid && dut.mac_in_ready) partial_terms=partial_terms+1;
            end
            pulse_reset;
            begin_job(0,job_layers[0],0,1); success;

            // Abort with a write waiting for acknowledgement, then recover with
            // a different parameter set (and that job's own shift metadata).
            begin_job(JOBS-1,job_layers[JOBS-1],0,0);
            while (!(mem_req_valid && mem_req_ready && mem_req_write)) @(negedge clk);
            @(negedge clk);
            pulse_reset;
            begin_job(JOBS-1,job_layers[JOBS-1],0,1); success;
            $display("AB_RESET_RECOVERY_PASS");
        end
        $display("AB_REGRESSION_PASS jobs=%0d rows=%0d inner=%0d cols=%0d",passed,ROWS,INNER,COLS);
        $finish;
    end
    initial begin
        #2000000000;
        $fatal(1,"AB regression watchdog timeout");
    end
endmodule
