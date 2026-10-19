`timescale 1ns/1ps
module tb_a_compute_adapter;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0, mac_clear=1, mac_in_valid=0, mac_out_ready=0;
    reg [15:0] mac_x=0, mac_w=0;
    reg [39:0] mac_bias=0;
    reg [5:0] mac_shift=0;
    reg mac_first=0, mac_last=0;
    wire mac_in_ready, mac_out_valid, mac_error;
    wire [15:0] mac_result;
    integer completed=0, faults_checked=0, clear_checked=0;
    a_compute_adapter dut(.*);

    // Independent longint reference: bias is added without wrapping to 40 bits.
    function automatic [15:0] reference_result(
        input longint signed sum, bias,
        input integer shift
    );
        longint signed total, magnitude, rounded;
        begin
            total=sum+bias;
            magnitude=(total<0) ? -total : total;
            if (shift==0) rounded=magnitude;
            else rounded=(magnitude+(64'sd1 << (shift-1))) >> shift;
            if (total<0) rounded=-rounded;
            if (rounded>32767) reference_result=16'h7fff;
            else if (rounded < -32768) reference_result=16'h8000;
            else reference_result=rounded[15:0];
        end
    endfunction

    task automatic wait_ready;
        begin
            while (mac_in_ready!==1'b1) @(negedge clk);
            if (mac_error!==0) $fatal(1,"ready with error");
        end
    endtask

    task automatic send_beat(
        input integer x_value, w_value,
        input reg first_value, last_value,
        input longint signed bias_value,
        input integer shift_value
    );
        begin
            @(negedge clk);
            mac_in_valid=1;mac_x=x_value[15:0];mac_w=w_value[15:0];
            mac_first=first_value;mac_last=last_value;
            mac_bias=bias_value[39:0];mac_shift=shift_value[5:0];
            @(posedge clk);
            while (mac_in_ready!==1'b1) @(posedge clk);
            @(negedge clk);mac_in_valid=0;
        end
    endtask

    task automatic clear_lane;
        reg was_released;
        begin
            @(negedge clk);was_released=dut.lane_rst_n;
            mac_clear=1;mac_in_valid=0;mac_out_ready=0;
            #1;
            if(dut.lane_rst_n!==was_released || mac_in_ready!==0 || mac_out_valid!==0)
                $fatal(1,"clear bypassed the clocked local reset or failed handshake isolation");
            repeat(3) begin
                @(posedge clk);#1;
                if (dut.lane_rst_n!==0 || mac_in_ready!==0 || mac_out_valid!==0 || mac_error!==0)
                    $fatal(1,"clear did not isolate/reset adapter");
            end
            @(negedge clk);mac_clear=0;
            // Deassertion cannot immediately enable a lane still in reset.
            #1;if(mac_in_ready!==0 || mac_out_valid!==0) $fatal(1,"reset release was not synchronized");
            repeat(2) begin
                @(posedge clk);#1;
                if(dut.lane_rst_n!==0 || mac_in_ready!==0)
                    $fatal(1,"local reset released before both synchronization stages");
            end
            wait_ready;
            repeat(5) begin
                @(negedge clk);
                if(mac_out_valid!==0 || mac_error!==0) $fatal(1,"ghost output/error after clear");
            end
            clear_checked=clear_checked+1;
        end
    endtask

    task automatic receive_result(input reg [15:0] expected, input integer stalls);
        reg [15:0] held;
        begin
            while(mac_out_valid!==1'b1) begin
                @(negedge clk);
                if(mac_error!==0) $fatal(1,"unexpected adapter error");
            end
            held=mac_result;
            if(held!==expected) $fatal(1,"adapter result expected=%h got=%h",expected,held);
            // A second dot must not start before the current output is taken.
            repeat(stalls+1) begin
                @(posedge clk);#1;
                if(mac_out_valid!==1 || mac_result!==held || mac_in_ready!==0 || mac_error!==0)
                    $fatal(1,"single-in-flight or output backpressure violation");
            end
            @(negedge clk);mac_out_ready=1;
            @(posedge clk);
            @(negedge clk);mac_out_ready=0;
            if(mac_out_valid!==0 || mac_error!==0) $fatal(1,"result handshake did not drain output");
            completed=completed+1;
        end
    endtask

    task automatic run_dot(
        input integer pattern,
        input longint signed bias_value,
        input integer shift_value, gaps, stalls
    );
        longint signed sum;
        integer x_value,w_value;
        reg [15:0] expected;
        begin
            wait_ready;sum=0;
            for(integer k=0;k<64;k=k+1) begin
                case(pattern)
                    0: begin x_value=0;w_value=0;end
                    1: begin x_value=1;w_value=1;end
                    2: begin x_value=-32768;w_value=32767;end
                    3: begin x_value=32767;w_value=32767;end
                    default: begin x_value=(k%2) ? -123 : 321;w_value=k-31;end
                endcase
                sum=sum+64'(x_value)*64'(w_value);
                if(gaps && k%7==0) repeat(3) @(negedge clk);
                // Later metadata is poisoned: only the first accepted pair counts.
                send_beat(x_value,w_value,k==0,k==63,
                    (k==0) ? bias_value : 64'sh123456789a,
                    (k==0) ? shift_value : 63);
            end
            expected=reference_result(sum,bias_value,shift_value);
            receive_result(expected,stalls);
            $display("DOT_PASS pattern=%0d shift=%0d expected=%h",pattern,shift_value,expected);
        end
    endtask

    task automatic expect_boundary_fault;
        begin
            if(mac_error!==1) $fatal(1,"boundary fault was not reported");
            repeat(6) begin
                @(posedge clk);#1;
                if(mac_error!==1 || mac_in_ready!==0 || mac_out_valid!==0)
                    $fatal(1,"boundary error was not sticky/isolated");
            end
            faults_checked=faults_checked+1;
            clear_lane;
        end
    endtask

    initial begin
        repeat(3) @(negedge clk);
        rst_n=1;
        clear_lane;
        run_dot(1,0,0,0,0);
        run_dot(4,-700,0,1,7);
        run_dot(0,32768,16,1,8);    // +0.5 -> +1
        run_dot(0,-32768,16,0,5);   // -0.5 -> -1
        run_dot(0,65536,17,1,6);
        run_dot(0,-65536,17,1,3);
        run_dot(0,32767,16,0,1);    // immediately below half -> zero
        run_dot(0,-32767,16,0,2);
        run_dot(0,65535,0,0,3);     // positive saturation
        run_dot(0,-65536,0,0,2);    // negative saturation
        run_dot(3,64'sd549755813887,16,1,10); // signed41 bias sum
        run_dot(2,-64'sd549755813888,16,1,9);
        run_dot(3,64'sd549755813887,63,1,4);
        run_dot(2,-64'sd549755813888,63,1,4);

        // The first accepted pair must carry first, not an implicit start.
        send_beat(1,1,0,0,0,0);
        expect_boundary_fault;
        // Early last, unexpected first, and missing final last are distinct errors.
        for(integer k=0;k<5;k=k+1) send_beat(1,1,k==0,0,0,0);
        send_beat(1,1,0,1,0,0);
        expect_boundary_fault;
        send_beat(1,1,1,0,0,0);
        send_beat(1,1,1,0,0,0);
        expect_boundary_fault;
        for(integer k=0;k<64;k=k+1) send_beat(1,1,k==0,0,0,0);
        expect_boundary_fault;

        // Clear a partial dot, then verify a complete fresh dot.
        for(integer k=0;k<17;k=k+1) send_beat(-9,13,k==0,0,-5,16);
        clear_lane;
        run_dot(1,-10,0,1,3);
        // Clear a pending, backpressured output before it is acknowledged.
        for(integer k=0;k<64;k=k+1) send_beat(7,5,k==0,k==63,0,0);
        while(mac_out_valid!==1'b1) @(negedge clk);
        // Keep a real next input pending under backpressure, then cancel it by
        // clear. A sender may not withdraw valid before acceptance otherwise.
        @(negedge clk);mac_in_valid=1;mac_first=1;mac_last=0;
        mac_x=7;mac_w=5;mac_bias=0;mac_shift=0;
        repeat(5) begin
            @(posedge clk);#1;
            if(mac_in_ready!==0 || mac_out_valid!==1 || mac_result!==16'd2240)
                $fatal(1,"pending input/output backpressure failed");
        end
        clear_lane;
        run_dot(1,-128,0,0,4);
        // The global reset also aborts a partial dot and synchronizes release.
        for(integer k=0;k<9;k=k+1) send_beat(3,-8,k==0,0,0,17);
        @(negedge clk);rst_n=0;
        #1;if(mac_in_ready!==0 || mac_out_valid!==0) $fatal(1,"global reset not isolated");
        repeat(3) @(negedge clk);
        rst_n=1;
        wait_ready;
        run_dot(4,42,0,1,6);
        if(completed!=17 || faults_checked!=4 || clear_checked!=7)
            $fatal(1,"unit test coverage count mismatch completed=%0d faults=%0d clears=%0d",completed,faults_checked,clear_checked);
        $display("A_ADAPTER_UNIT_PASS dots=%0d boundary_faults=%0d clears=%0d",completed,faults_checked,clear_checked);
        $finish;
    end
    initial begin
        #1000000;
        $fatal(1,"adapter unit watchdog timeout");
    end
endmodule
