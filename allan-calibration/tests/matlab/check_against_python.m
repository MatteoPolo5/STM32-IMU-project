% Cross-check: the MATLAB/Octave tools must reproduce the numbers of the Python tools.
%   octave --eval "check_against_python('data/synthetic.bin', 'results/synthetic/summary.json')"
function check_against_python(binfile, jsonfile)
    addpath(fullfile(fileparts(mfilename('fullpath')), '..', '..', 'tools', 'matlab'));
    ref = jsondecode(fileread(jsonfile));
    r = analyze_log(binfile);

    assert(r.frames_received == ref.loss.frames_received, 'frames_received differs');
    assert(r.frames_lost == ref.loss.frames_lost, 'frames_lost differs');
    assert(r.crc_errors == ref.loss.crc_errors, 'crc_errors differs');
    assert(abs(r.jitter_rms_us - ref.timing.jitter_us.rms) < 1e-6, 'jitter rms differs');
    assert(abs(r.latency_mean_us - ref.timing.latency_us.mean) < 1e-6, 'latency differs');
    assert(max(abs(r.gyro_bias_dps - ref.imu_static.gyro_mean_dps(:).')) < 1e-4, 'gyro bias differs');
    names = {'x', 'y', 'z'};
    for i = 1:3
        ref_a = ref.allan_gyro.(names{i});
        assert(abs(r.allan_arw_deg_per_sqrt_h(i) - ref_a.arw_deg_per_sqrt_h) < 1e-6 * ref_a.arw_deg_per_sqrt_h, 'Allan ARW differs');
        assert(abs(r.allan_slope_at_1s(i) - ref_a.slope_at_1s) < 1e-6, 'Allan slope differs');
        assert(r.allan_bias_instability_observed(i) == ref_a.bias_instability_observed, 'Allan observed flag differs');
    end
    disp('OK: MATLAB/Octave results match the Python reference');
end
