function report = analyze_log(filename, rate_hz, cpu_hz, accel_fs, gyro_fs)
%ANALYZE_LOG  Loss, timing and static-IMU statistics of a capture from the E3 firmware.
%   report = analyze_log('data/capture.bin')
%   report = analyze_log('data/capture.bin', 1000, 84e6, 0, 0)
%
%   rate_hz   nominal sample rate = SAMPLE_RATE_HZ in the firmware      (default 1000)
%   cpu_hz    core clock = DWT cycle counter frequency                  (default 84e6)
%   accel_fs  MPU_ACCEL_FS_SEL used in the firmware (0..3)              (default 0)
%   gyro_fs   MPU_GYRO_FS_SEL used in the firmware (0..3)               (default 0)
%
% Same quantities as the Python tool (tools/imu_daq), so results can be cross-checked.

if nargin < 2, rate_hz  = 1000; end
if nargin < 3, cpu_hz   = 84e6; end
if nargin < 4, accel_fs = 0;    end
if nargin < 5, gyro_fs  = 0;    end

acc_lsb  = [16384 8192 4096 2048];
gyro_lsb = [131 65.5 32.8 16.4];

L = parse_log(filename);
N = numel(L.seq);
if N < 10, error('only %d valid frames found', N); end

% ---- loss -------------------------------------------------------------------
d = diff(L.seq);
gaps = d(d > 1) - 1;
expected = L.seq(end) - L.seq(1) + 1;   % assumes the capture is in order (checked below)
report.frames_received = N;
report.frames_expected = expected;
report.frames_lost     = sum(gaps);
report.loss_percent    = 100 * sum(gaps) / expected;
report.out_of_order    = sum(d <= 0);
report.crc_errors      = L.n_bad_crc;
report.firmware_dropped_last = L.dropped(end);

% ---- timing (only consecutive samples, so lost frames do not pollute the jitter) ----
dt = mod(diff(L.t_tick), 2^32);         % wrap-safe difference of a 32-bit counter
dt = dt(d == 1);
ideal = cpu_hz / rate_hz;               % cycles
err_us = (dt - ideal) * 1e6 / cpu_hz;
report.rate_hz_measured = cpu_hz / mean(dt);
report.jitter_rms_us    = sqrt(mean(err_us.^2));
report.jitter_pp_us     = max(err_us) - min(err_us);
report.jitter_maxabs_us = max(abs(err_us));
lat_us = mod(L.t_done - L.t_tick, 2^32) * 1e6 / cpu_hz;
report.latency_mean_us = mean(lat_us);
report.latency_max_us  = max(lat_us);

% ---- static IMU ---------------------------------------------------------------
acc  = L.counts(:, 1:3) / acc_lsb(accel_fs + 1);   % [g]
gyro = L.counts(:, 5:7) / gyro_lsb(gyro_fs + 1);   % [deg/s]
report.acc_mean_g      = mean(acc);
report.acc_std_mg      = std(acc) * 1e3;
report.acc_norm_err_mg = (mean(sqrt(sum(acc.^2, 2))) - 1) * 1e3;
report.gyro_bias_dps   = mean(gyro);
report.gyro_std_dps    = std(gyro);

% ---- gyro Allan deviation ------------------------------------------------------
report.allan_arw_deg_per_sqrt_h = NaN(1, 3);
report.allan_slope_at_1s = NaN(1, 3);
report.allan_bias_instability_deg_per_h = NaN(1, 3);
report.allan_bias_instability_observed = false(1, 3);
for i = 1:3
    [tau_, adev_] = allan_deviation(gyro(:, i), rate_hz);
    a_ = allan_summary(tau_, adev_);
    report.allan_arw_deg_per_sqrt_h(i) = a_.arw_deg_per_sqrt_h;
    report.allan_slope_at_1s(i) = a_.slope_at_1s;
    report.allan_bias_instability_deg_per_h(i) = a_.bias_instability_deg_per_h;
    report.allan_bias_instability_observed(i) = a_.bias_instability_observed;
end

% ---- print --------------------------------------------------------------------
fprintf('frames: %d received / %d expected, lost %d (%.4f %%), crc errors %d, out of order %d\n', ...
        N, expected, report.frames_lost, report.loss_percent, L.n_bad_crc, report.out_of_order);
fprintf('rate: nominal %.1f Hz, measured %.3f Hz\n', rate_hz, report.rate_hz_measured);
fprintf('jitter: rms %.3f us, peak-to-peak %.3f us, max |err| %.3f us\n', ...
        report.jitter_rms_us, report.jitter_pp_us, report.jitter_maxabs_us);
fprintf('latency tick->DMA done: mean %.1f us, max %.1f us\n', report.latency_mean_us, report.latency_max_us);
fprintf('static IMU: |a| error %+.1f mg, gyro bias [%.4f %.4f %.4f] deg/s\n', ...
        report.acc_norm_err_mg, report.gyro_bias_dps);

fprintf('gyro Allan ARW [%.3f %.3f %.3f] deg/sqrt(h) (slope at 1 s [%+.2f %+.2f %+.2f]); bias instability observed: [%d %d %d]\n', ...
        report.allan_arw_deg_per_sqrt_h, report.allan_slope_at_1s, report.allan_bias_instability_observed);

% ---- plots (skipped when no display is available) -----------------------------
if usejava('desktop')
    figure('Name', 'E3 timing');
    subplot(1,2,1); plot(err_us); xlabel('sample'); ylabel('interval - ideal [\mus]'); title('Sampling interval error'); grid on;
    subplot(1,2,2); hist(err_us, 80); xlabel('interval - ideal [\mus]'); ylabel('count'); title('Jitter histogram'); grid on;
    figure('Name', 'E3 IMU');
    subplot(2,1,1); plot(acc);  ylabel('accel [g]');      legend('x','y','z'); grid on;
    subplot(2,1,2); plot(gyro); ylabel('gyro [deg/s]'); xlabel('sample'); grid on;
end
end
