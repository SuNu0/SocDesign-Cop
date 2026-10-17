`timescale 1ns/1ps
module tb_a_compute;
    localparam MAX_DOTS=10000;
    localparam MAX_RQ=5000;
    logic clk=0;
    always #3.333 clk=~clk;
    logic rst_n=0;
    logic dv=0,dr,da_ready=0,dov;
    logic signed [15:0] dx=0,dw=0;
    logic signed [39:0] dacc;
    logic lv=0,lr,lo_ready=0,lov;
    logic signed [15:0] lx=0,lw=0,lo;
    logic signed [39:0] lb=0;
    logic [5:0] ls=0;
    logic rv=0,rr,ro_ready=0,rov;
    logic signed [39:0] ra=0,rb=0;
    logic [5:0] rs=0;
    logic signed [15:0] ro;
    dot64_mac mac(clk,rst_n,dv,dr,dx,dw,dov,da_ready,dacc);
    compute_lane lane(clk,rst_n,lv,lr,lx,lw,lb,ls,lov,lo_ready,lo);
    bias_requant rq(clk,rst_n,rv,rr,ra,rb,rs,rov,ro_ready,ro);
    logic [15:0] xs[0:MAX_DOTS*64-1],ws[0:MAX_DOTS*64-1];
    logic [39:0] bs[0:MAX_DOTS-1],accs[0:MAX_DOTS-1];
    logic [7:0] shifts[0:MAX_DOTS-1];
    logic [15:0] expected[0:MAX_DOTS-1];
    logic [39:0] rq_as[0:MAX_RQ-1],rq_bs[0:MAX_RQ-1];
    logic [7:0] rq_shifts[0:MAX_RQ-1];
    logic [15:0] rq_expected[0:MAX_RQ-1];
    integer n_dots,n_rq;
    integer phase=0,d_seen=0,l_seen=0,r_seen=0;
    integer d_accepted=0,l_accepted=0,r_accepted=0;
    integer input_gap_cycles=0,output_stall_cycles=0;
    logic d_stall=0,l_stall=0,r_stall=0;
    logic [39:0] held_acc;
    logic [15:0] held_lane,held_rq;
    logic [31:0] random_state=32'h13579bdf;
    string dir;
    integer i,beat,j;
    always @(negedge clk) begin
        random_state = {random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
        if (phase==1) da_ready = random_state[0] | random_state[5];
        if (phase==2) lo_ready = random_state[1] | random_state[6];
        if (phase==3) ro_ready = random_state[2] | random_state[7];
    end
    always @(posedge clk) begin
        if (!rst_n) begin
            d_stall=0;l_stall=0;r_stall=0;
        end else begin
            if (d_stall && (!dov || dacc!==held_acc)) $fatal(1,"MAC changed during backpressure");
            if (l_stall && (!lov || lo!==held_lane)) $fatal(1,"LANE changed during backpressure");
            if (r_stall && (!rov || ro!==held_rq)) $fatal(1,"REQUANT changed during backpressure");
            d_stall=dov&&!da_ready;held_acc=dacc;
            l_stall=lov&&!lo_ready;held_lane=lo;
            r_stall=rov&&!ro_ready;held_rq=ro;
            if ((dov&&!da_ready)||(lov&&!lo_ready)||(rov&&!ro_ready)) output_stall_cycles++;
            if (phase==1) begin
                if (dv&&dr) d_accepted++;
                if (!dv&&dr) input_gap_cycles++;
                if (dov&&da_ready) begin
                    if (d_seen>=n_dots || dacc!==accs[d_seen])
                        $fatal(1,"MAC case %0d expected %h got %h",d_seen,accs[d_seen],dacc);
                    d_seen++;
                end
            end
            if (phase==2) begin
                if (lv&&lr) l_accepted++;
                if (!lv&&lr) input_gap_cycles++;
                if (lov&&lo_ready) begin
                    if (l_seen>=n_dots || lo!==expected[l_seen])
                        $fatal(1,"LANE case %0d expected %h got %h",l_seen,expected[l_seen],lo);
                    l_seen++;
                end
            end
            if (phase==3) begin
                if (rv&&rr) r_accepted++;
                if (rov&&ro_ready) begin
                    if (r_seen>=n_rq || ro!==rq_expected[r_seen])
                        $fatal(1,"REQUANT case %0d expected %h got %h",r_seen,rq_expected[r_seen],ro);
                    r_seen++;
                end
            end
        end
    end
    task reset_all;
        begin
            @(negedge clk);rst_n=0;dv=0;lv=0;rv=0;
            da_ready=0;lo_ready=0;ro_ready=0;
            repeat(3) @(negedge clk);
            if (dov!==0||lov!==0||rov!==0) $fatal(1,"Reset did not clear output valid");
            rst_n=1;
        end
    endtask
    initial begin
        if (!$value$plusargs("VECTORS=%s",dir)) $fatal(1,"Missing VECTORS");
        if (!$value$plusargs("DOT_CASES=%d",n_dots)) $fatal(1,"Missing DOT_CASES");
        if (!$value$plusargs("RQ_CASES=%d",n_rq)) $fatal(1,"Missing RQ_CASES");
        if(n_dots>MAX_DOTS||n_rq>MAX_RQ||n_dots<1||n_rq<1) $fatal(1,"Invalid vector counts");
        $readmemh({dir,"/x.hex"},xs,0,n_dots*64-1);
        $readmemh({dir,"/w.hex"},ws,0,n_dots*64-1);
        $readmemh({dir,"/b.hex"},bs,0,n_dots-1);
        $readmemh({dir,"/shift.hex"},shifts,0,n_dots-1);
        $readmemh({dir,"/acc.hex"},accs,0,n_dots-1);
        $readmemh({dir,"/expected.hex"},expected,0,n_dots-1);
        $readmemh({dir,"/rq_acc.hex"},rq_as,0,n_rq-1);
        $readmemh({dir,"/rq_b.hex"},rq_bs,0,n_rq-1);
        $readmemh({dir,"/rq_shift.hex"},rq_shifts,0,n_rq-1);
        $readmemh({dir,"/rq_expected.hex"},rq_expected,0,n_rq-1);
        reset_all();
        // Abort a PARTIAL dot, then abort PENDING MAC/lane/requant results.
        @(negedge clk);dv=1;lv=1;dx=1;dw=1;lx=1;lw=1;
        repeat(19) @(negedge clk);
        reset_all();
        @(negedge clk);dv=1;lv=1;rv=1;dx=1;dw=1;lx=1;lw=1;ra=5;rb=0;rs=0;
        repeat(64) @(posedge clk);
        @(negedge clk);dv=0;lv=0;rv=0;
        repeat(5) @(negedge clk);
        if (!dov||!lov||!rov) $fatal(1,"Reset-pending setup incomplete");
        reset_all();
        repeat(5) @(negedge clk);
        if(dov||lov||rov) $fatal(1,"Ghost output after reset");
        $display("RESET_ABORT_TESTS_PASSED");
        phase=1;
        for(i=0;i<n_dots*64;i=i+1) begin
            // First cases: continuous valid, later cases deterministic input gaps.
            if(i>=64*8 && i%11==0) begin
                @(negedge clk);dv=0;repeat(2) @(posedge clk);
            end
            @(negedge clk);dx=xs[i];dw=ws[i];dv=1;
            @(posedge clk);while(!dr) @(posedge clk);
        end
        @(negedge clk);dv=0;
        wait(d_seen==n_dots);
        repeat(5) @(negedge clk);
        if(d_accepted!=n_dots*64) $fatal(1,"MAC input count mismatch");
        $display("DOT64_TESTS_PASSED count=%0d",d_seen);
        phase=0;reset_all();phase=2;
        for(i=0;i<n_dots*64;i=i+1) begin
            if(i>=64*8 && i%13==0) begin
                @(negedge clk);lv=0;repeat(3) @(posedge clk);
            end
            @(negedge clk);lx=xs[i];lw=ws[i];lv=1;
            // Deliberately poison metadata after the first beat: it MUST be ignored.
            lb=(i%64==0)?bs[i/64]:40'h123456789a;
            ls=(i%64==0)?shifts[i/64][5:0]:6'd63;
            @(posedge clk);while(!lr) @(posedge clk);
        end
        @(negedge clk);lv=0;
        wait(l_seen==n_dots);
        repeat(5) @(negedge clk);
        if(l_accepted!=n_dots*64) $fatal(1,"LANE input count mismatch");
        $display("COMPUTE_LANE_TESTS_PASSED count=%0d",l_seen);
        phase=0;reset_all();phase=3;
        for(j=0;j<n_rq;j=j+1) begin
            @(negedge clk);ra=rq_as[j];rb=rq_bs[j];rs=rq_shifts[j][5:0];rv=1;
            @(posedge clk);while(!rr) @(posedge clk);
        end
        @(negedge clk);rv=0;
        wait(r_seen==n_rq);
        repeat(5) @(negedge clk);
        if(r_accepted!=n_rq) $fatal(1,"REQUANT input count mismatch");
        if(input_gap_cycles==0||output_stall_cycles==0) $fatal(1,"Missing gap/stall stimulus");
        $display("BIAS_REQUANT_TESTS_PASSED count=%0d",r_seen);
        $display("PROTOCOL_COVERAGE input_gap_cycles=%0d output_stall_cycles=%0d",input_gap_cycles,output_stall_cycles);
        $display("ALL_A_COMPUTE_TESTS_PASSED dots=%0d requant=%0d",n_dots,n_rq);
        $finish;
    end
    initial begin
        #100000000;
        $fatal(1,"WATCHDOG phase=%0d mac=%0d lane=%0d rq=%0d",phase,d_seen,l_seen,r_seen);
    end
endmodule
